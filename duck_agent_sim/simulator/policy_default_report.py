from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from duck_agent_sim.simulator.policy_contract import (
    ACTUATOR_ORDER,
    DEFAULT_ACTUATOR,
    POLICY_OUTPUT_SIZE,
)


@dataclass(frozen=True)
class ActuatorDefaultDelta:
    name: str
    index: int
    default_value: float
    home_ctrl_value: float
    delta: float
    abs_delta: float


@dataclass(frozen=True)
class PolicyDefaultAlignmentReport:
    actuator_count: int
    tolerance: float
    max_abs_delta: float
    within_tolerance: bool
    deltas: tuple[ActuatorDefaultDelta, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "actuator_count": self.actuator_count,
            "tolerance": self.tolerance,
            "max_abs_delta": self.max_abs_delta,
            "within_tolerance": self.within_tolerance,
            "deltas": [
                {
                    "name": delta.name,
                    "index": delta.index,
                    "default_value": delta.default_value,
                    "home_ctrl_value": delta.home_ctrl_value,
                    "delta": delta.delta,
                    "abs_delta": delta.abs_delta,
                }
                for delta in self.deltas
            ],
        }


def compare_default_actuator_to_home_ctrl(
    home_ctrl: np.ndarray,
    *,
    tolerance: float = 5e-3,
    actuator_names: list[str] | tuple[str, ...] = ACTUATOR_ORDER,
) -> PolicyDefaultAlignmentReport:
    home_ctrl_array = np.asarray(home_ctrl, dtype=np.float32)
    default_array = np.asarray(DEFAULT_ACTUATOR, dtype=np.float32)

    if home_ctrl_array.shape != (POLICY_OUTPUT_SIZE,):
        raise ValueError(
            f"home_ctrl must have shape ({POLICY_OUTPUT_SIZE},), "
            f"got {home_ctrl_array.shape}"
        )
    if len(actuator_names) != POLICY_OUTPUT_SIZE:
        raise ValueError(
            f"actuator_names must contain {POLICY_OUTPUT_SIZE} names, "
            f"got {len(actuator_names)}"
        )

    raw_delta = home_ctrl_array - default_array
    deltas = tuple(
        ActuatorDefaultDelta(
            name=str(name),
            index=index,
            default_value=float(default_array[index]),
            home_ctrl_value=float(home_ctrl_array[index]),
            delta=float(raw_delta[index]),
            abs_delta=float(abs(raw_delta[index])),
        )
        for index, name in enumerate(actuator_names)
    )
    max_abs_delta = max((delta.abs_delta for delta in deltas), default=0.0)
    return PolicyDefaultAlignmentReport(
        actuator_count=len(deltas),
        tolerance=float(tolerance),
        max_abs_delta=float(max_abs_delta),
        within_tolerance=bool(max_abs_delta <= tolerance),
        deltas=deltas,
    )


def compare_model_home_ctrl_to_policy_default(
    model: Any,
    *,
    tolerance: float = 5e-3,
) -> PolicyDefaultAlignmentReport:
    actuator_names = [model.actuator(k).name for k in range(model.nu)]
    home_ctrl = np.asarray(model.keyframe("home").ctrl, dtype=np.float32)
    return compare_default_actuator_to_home_ctrl(
        home_ctrl,
        tolerance=tolerance,
        actuator_names=actuator_names,
    )
