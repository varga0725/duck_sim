from __future__ import annotations

from dataclasses import dataclass

import numpy as np

OBSERVATION_SIZE = 101
POLICY_OUTPUT_SIZE = 14
ACTION_SCALE = 0.25
DOF_VEL_SCALE = 0.05
MAX_MOTOR_VELOCITY = 5.24
SIM_DT = 0.002
DECIMATION = 10
MAX_TARGET_DELTA_PER_POLICY_STEP = MAX_MOTOR_VELOCITY * (SIM_DT * DECIMATION)

ACTUATOR_ORDER = [
    "left_hip_yaw",
    "left_hip_roll",
    "left_hip_pitch",
    "left_knee",
    "left_ankle",
    "neck_pitch",
    "head_pitch",
    "head_yaw",
    "head_roll",
    "right_hip_yaw",
    "right_hip_roll",
    "right_hip_pitch",
    "right_knee",
    "right_ankle",
]

DEFAULT_ACTUATOR = np.array(
    [
        0.002,
        0.053,
        -0.630,
        1.368,
        -0.784,
        0.000,
        0.000,
        0.000,
        0.000,
        -0.003,
        -0.065,
        0.635,
        1.379,
        -0.796,
    ],
    dtype=np.float32,
)

ACTUATOR_CTRL_RANGES = np.array(
    [
        [-0.523599, 0.523599],
        [-0.436332, 0.436332],
        [-1.221730, 0.523599],
        [-1.570796, 1.570796],
        [-1.570796, 1.570796],
        [-0.349066, 1.134464],
        [-0.785398, 0.785398],
        [-2.792527, 2.792527],
        [-0.523599, 0.523599],
        [-0.523599, 0.523599],
        [-0.436332, 0.436332],
        [-0.523599, 1.221730],
        [-1.570796, 1.570796],
        [-1.570796, 1.570796],
    ],
    dtype=np.float32,
)


@dataclass(frozen=True)
class PolicyCommandLimits:
    linear_x: tuple[float, float] = (-0.15, 0.15)
    linear_y: tuple[float, float] = (-0.2, 0.2)
    yaw: tuple[float, float] = (-1.0, 1.0)


POLICY_COMMAND_LIMITS = PolicyCommandLimits()


@dataclass(frozen=True)
class ClampedControl:
    linear_x: float
    linear_y: float
    yaw: float


def _as_policy_action(action: np.ndarray) -> np.ndarray:
    action_array = np.asarray(action, dtype=np.float32)
    if action_array.shape != (POLICY_OUTPUT_SIZE,):
        raise ValueError(
            f"Policy action must have shape ({POLICY_OUTPUT_SIZE},), "
            f"got {action_array.shape}"
        )
    return action_array


def clamp_targets_to_ctrlrange(targets: np.ndarray) -> np.ndarray:
    target_array = np.asarray(targets, dtype=np.float32)
    if target_array.shape != (POLICY_OUTPUT_SIZE,):
        raise ValueError(
            f"Motor targets must have shape ({POLICY_OUTPUT_SIZE},), "
            f"got {target_array.shape}"
        )
    return np.clip(target_array, ACTUATOR_CTRL_RANGES[:, 0], ACTUATOR_CTRL_RANGES[:, 1])


def apply_action_to_targets(action: np.ndarray) -> np.ndarray:
    """Map raw ONNX continuous_actions to safe actuator position targets."""
    raw_targets = DEFAULT_ACTUATOR + _as_policy_action(action) * ACTION_SCALE
    return clamp_targets_to_ctrlrange(raw_targets)


def apply_target_rate_limit(
    targets: np.ndarray,
    previous_targets: np.ndarray,
) -> np.ndarray:
    target_array = clamp_targets_to_ctrlrange(targets)
    previous_array = clamp_targets_to_ctrlrange(previous_targets)
    limited = np.clip(
        target_array,
        previous_array - MAX_TARGET_DELTA_PER_POLICY_STEP,
        previous_array + MAX_TARGET_DELTA_PER_POLICY_STEP,
    )
    return clamp_targets_to_ctrlrange(limited)


def clamp_control_to_policy_limits(
    linear_x: float, linear_y: float, yaw: float
) -> ClampedControl:
    return ClampedControl(
        linear_x=float(np.clip(linear_x, *POLICY_COMMAND_LIMITS.linear_x)),
        linear_y=float(np.clip(linear_y, *POLICY_COMMAND_LIMITS.linear_y)),
        yaw=float(np.clip(yaw, *POLICY_COMMAND_LIMITS.yaw)),
    )
