from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from duck_agent_sim.simulator.policy_contract import (
    ACTUATOR_ORDER,
    DECIMATION,
    DOF_VEL_SCALE,
    OBSERVATION_SIZE,
    POLICY_OUTPUT_SIZE,
    SIM_DT,
    apply_action_to_targets,
    apply_target_rate_limit,
)
from duck_agent_sim.simulator.policy_default_report import (
    PolicyDefaultAlignmentReport,
    compare_default_actuator_to_home_ctrl,
)


@dataclass
class UpstreamPolicyState:
    motor_targets: np.ndarray
    prev_motor_targets: np.ndarray
    last_action: np.ndarray = field(default_factory=lambda: np.zeros(POLICY_OUTPUT_SIZE, dtype=np.float32))
    last_last_action: np.ndarray = field(default_factory=lambda: np.zeros(POLICY_OUTPUT_SIZE, dtype=np.float32))
    last_last_last_action: np.ndarray = field(default_factory=lambda: np.zeros(POLICY_OUTPUT_SIZE, dtype=np.float32))
    imitation_i: float = 0.0
    imitation_phase: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0], dtype=np.float32))
    nb_steps_in_period: int = 50

    @classmethod
    def from_default_targets(cls, targets: np.ndarray) -> "UpstreamPolicyState":
        target_array = np.asarray(targets, dtype=np.float32)
        if target_array.shape != (POLICY_OUTPUT_SIZE,):
            raise ValueError(
                f"targets must have shape ({POLICY_OUTPUT_SIZE},), "
                f"got {target_array.shape}"
            )
        return cls(
            motor_targets=target_array.copy(),
            prev_motor_targets=target_array.copy(),
        )


@dataclass(frozen=True)
class UpstreamPolicyAdapterSpec:
    sim_dt: float = SIM_DT
    decimation: int = DECIMATION
    dof_vel_scale: float = DOF_VEL_SCALE
    policy_output_size: int = POLICY_OUTPUT_SIZE

    @property
    def physics_rate_hz(self) -> float:
        return 1.0 / self.sim_dt

    @property
    def policy_rate_hz(self) -> float:
        return self.physics_rate_hz / self.decimation


class UpstreamPolicyExecutionAdapter:
    """
    Non-runtime scaffold for the future upstream-aligned policy execution boundary.

    The adapter intentionally does not run ONNX inference, build observations, write
    MuJoCo controls, or step physics yet. Phase 3C only fixes the interface shape so
    later work can move RealDuckSimulator policy mechanics behind a small boundary.
    """

    def __init__(self, spec: UpstreamPolicyAdapterSpec | None = None):
        self.spec = spec or UpstreamPolicyAdapterSpec()

    def initialize_state(self, default_targets: np.ndarray) -> UpstreamPolicyState:
        return UpstreamPolicyState.from_default_targets(default_targets)

    def expected_motor_targets(
        self,
        action: np.ndarray,
        previous_targets: np.ndarray,
    ) -> np.ndarray:
        targets = apply_action_to_targets(action)
        return apply_target_rate_limit(targets, previous_targets)

    def shadow_compare(
        self,
        *,
        local_observation: np.ndarray,
        action: np.ndarray,
        local_motor_targets: np.ndarray,
        previous_targets: np.ndarray,
        home_ctrl: np.ndarray,
        actuator_names: list[str] | tuple[str, ...] = ACTUATOR_ORDER,
        command_vector: np.ndarray | None = None,
        upstream_command_vector: np.ndarray | None = None,
        local_phase_period: int = 50,
        upstream_phase_period: int | None = None,
    ) -> "UpstreamPolicyShadowReport":
        obs = np.asarray(local_observation, dtype=np.float32)
        action_array = np.asarray(action, dtype=np.float32)
        local_targets = np.asarray(local_motor_targets, dtype=np.float32)
        expected_targets = self.expected_motor_targets(action_array, previous_targets)
        target_delta = local_targets - expected_targets

        command_mismatch = False
        max_command_delta = 0.0
        if command_vector is not None and upstream_command_vector is not None:
            command_delta = np.asarray(command_vector, dtype=np.float32) - np.asarray(upstream_command_vector, dtype=np.float32)
            max_command_delta = float(np.max(np.abs(command_delta))) if command_delta.size else 0.0
            command_mismatch = bool(max_command_delta > 1e-6)

        upstream_period = upstream_phase_period if upstream_phase_period is not None else local_phase_period
        return UpstreamPolicyShadowReport(
            observation_shape=tuple(obs.shape),
            observation_shape_ok=obs.shape == (OBSERVATION_SIZE,),
            action_shape=tuple(action_array.shape),
            action_shape_ok=action_array.shape == (POLICY_OUTPUT_SIZE,),
            motor_target_shape=tuple(local_targets.shape),
            motor_target_shape_ok=local_targets.shape == (POLICY_OUTPUT_SIZE,),
            max_motor_target_delta=float(np.max(np.abs(target_delta))) if target_delta.size else 0.0,
            default_alignment=compare_default_actuator_to_home_ctrl(
                home_ctrl,
                actuator_names=actuator_names,
            ),
            actuator_order_ok=list(actuator_names) == ACTUATOR_ORDER,
            local_phase_period=int(local_phase_period),
            upstream_phase_period=int(upstream_period),
            phase_timing_mismatch=int(local_phase_period) != int(upstream_period),
            command_mismatch=command_mismatch,
            max_command_delta=max_command_delta,
        )


@dataclass(frozen=True)
class UpstreamPolicyShadowReport:
    observation_shape: tuple[int, ...]
    observation_shape_ok: bool
    action_shape: tuple[int, ...]
    action_shape_ok: bool
    motor_target_shape: tuple[int, ...]
    motor_target_shape_ok: bool
    max_motor_target_delta: float
    default_alignment: PolicyDefaultAlignmentReport
    actuator_order_ok: bool
    local_phase_period: int
    upstream_phase_period: int
    phase_timing_mismatch: bool
    command_mismatch: bool
    max_command_delta: float

    @property
    def ok(self) -> bool:
        return (
            self.observation_shape_ok
            and self.action_shape_ok
            and self.motor_target_shape_ok
            and self.actuator_order_ok
            and not self.phase_timing_mismatch
            and not self.command_mismatch
        )
