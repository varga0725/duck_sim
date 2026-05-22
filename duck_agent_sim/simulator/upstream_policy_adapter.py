from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from duck_agent_sim.simulator.policy_contract import (
    DECIMATION,
    DOF_VEL_SCALE,
    POLICY_OUTPUT_SIZE,
    SIM_DT,
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
