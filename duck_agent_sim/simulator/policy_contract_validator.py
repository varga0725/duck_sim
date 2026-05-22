from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from duck_agent_sim.simulator.policy_contract import (
    ACTION_SCALE,
    ACTUATOR_CTRL_RANGES,
    ACTUATOR_ORDER,
    DECIMATION,
    DEFAULT_ACTUATOR,
    DOF_VEL_SCALE,
    OBSERVATION_SIZE,
    POLICY_COMMAND_LIMITS,
    POLICY_OUTPUT_SIZE,
    SIM_DT,
)


COMMAND_SLICE = slice(6, 13)
EXPECTED_ONNX_INPUT_NAME = "obs"
EXPECTED_ONNX_OUTPUT_NAME = "continuous_actions"
EXPECTED_ONNX_DTYPE = "tensor(float)"
EXPECTED_PHYSICS_RATE_HZ = 500.0
EXPECTED_POLICY_RATE_HZ = 50.0


@dataclass(frozen=True)
class ValidationIssue:
    check: str
    severity: str
    message: str
    expected: Any = None
    actual: Any = None


@dataclass
class ValidationReport:
    name: str
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def add(
        self,
        check: str,
        severity: str,
        message: str,
        *,
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                check=check,
                severity=severity,
                message=message,
                expected=expected,
                actual=actual,
            )
        )

    def extend(self, issues: Iterable[ValidationIssue]) -> None:
        self.issues.extend(issues)


def _shape_as_list(shape: Iterable[Any]) -> list[Any]:
    return [int(dim) if isinstance(dim, np.integer) else dim for dim in shape]


def validate_onnx_session(session: Any) -> ValidationReport:
    report = ValidationReport("onnx_model_contract")
    inputs = list(session.get_inputs())
    outputs = list(session.get_outputs())

    if len(inputs) != 1:
        report.add("onnx_input_count", "error", "ONNX model must expose one input.", expected=1, actual=len(inputs))
        return report
    if len(outputs) != 1:
        report.add("onnx_output_count", "error", "ONNX model must expose one output.", expected=1, actual=len(outputs))
        return report

    input_meta = inputs[0]
    output_meta = outputs[0]
    expected_input_shape = [1, OBSERVATION_SIZE]
    expected_output_shape = [1, POLICY_OUTPUT_SIZE]

    if input_meta.name != EXPECTED_ONNX_INPUT_NAME:
        report.add("onnx_input_name", "error", "Unexpected ONNX input name.", expected=EXPECTED_ONNX_INPUT_NAME, actual=input_meta.name)
    if _shape_as_list(input_meta.shape) != expected_input_shape:
        report.add("onnx_input_shape", "error", "Unexpected ONNX input shape.", expected=expected_input_shape, actual=_shape_as_list(input_meta.shape))
    if input_meta.type != EXPECTED_ONNX_DTYPE:
        report.add("onnx_input_dtype", "error", "Unexpected ONNX input dtype.", expected=EXPECTED_ONNX_DTYPE, actual=input_meta.type)

    if output_meta.name != EXPECTED_ONNX_OUTPUT_NAME:
        report.add("onnx_output_name", "error", "Unexpected ONNX output name.", expected=EXPECTED_ONNX_OUTPUT_NAME, actual=output_meta.name)
    if _shape_as_list(output_meta.shape) != expected_output_shape:
        report.add("onnx_output_shape", "error", "Unexpected ONNX output shape.", expected=expected_output_shape, actual=_shape_as_list(output_meta.shape))
    if output_meta.type != EXPECTED_ONNX_DTYPE:
        report.add("onnx_output_dtype", "error", "Unexpected ONNX output dtype.", expected=EXPECTED_ONNX_DTYPE, actual=output_meta.type)

    return report


def validate_onnx_model(model_path: str | Path) -> ValidationReport:
    import onnxruntime as ort

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    return validate_onnx_session(session)


def validate_command_values(linear_x: float, linear_y: float, yaw: float, *, atol: float = 1e-6) -> ValidationReport:
    report = ValidationReport("policy_command_limits")
    values = {
        "linear_x": (float(linear_x), POLICY_COMMAND_LIMITS.linear_x),
        "linear_y": (float(linear_y), POLICY_COMMAND_LIMITS.linear_y),
        "yaw": (float(yaw), POLICY_COMMAND_LIMITS.yaw),
    }
    for name, (value, limits) in values.items():
        if value < limits[0] - atol or value > limits[1] + atol:
            report.add(
                f"command_{name}_range",
                "error",
                f"Command {name} is outside policy limits.",
                expected=limits,
                actual=value,
            )
    return report


def validate_observation(obs: np.ndarray) -> ValidationReport:
    report = ValidationReport("observation_contract")
    obs_array = np.asarray(obs)

    if obs_array.shape != (OBSERVATION_SIZE,):
        report.add("observation_shape", "error", "Observation must be a flat 101-vector.", expected=(OBSERVATION_SIZE,), actual=obs_array.shape)
        return report
    if obs_array.dtype != np.float32:
        report.add("observation_dtype", "error", "Observation must be float32.", expected=np.dtype(np.float32), actual=obs_array.dtype)
    if not np.all(np.isfinite(obs_array)):
        report.add("observation_finite", "error", "Observation contains NaN or inf values.")

    command = obs_array[COMMAND_SLICE]
    command_report = validate_command_values(command[0], command[1], command[2])
    report.extend(command_report.issues)
    return report


def validate_mujoco_model(model: Any, *, home_ctrl_atol: float = 5e-3, ctrlrange_atol: float = 1e-6) -> ValidationReport:
    report = ValidationReport("mujoco_policy_contract")

    if int(model.nu) != POLICY_OUTPUT_SIZE:
        report.add("actuator_count", "error", "MuJoCo actuator count must match policy output size.", expected=POLICY_OUTPUT_SIZE, actual=int(model.nu))
        return report

    actuator_names = [model.actuator(k).name for k in range(model.nu)]
    if actuator_names != ACTUATOR_ORDER:
        report.add("actuator_order", "error", "MuJoCo actuator order differs from policy contract.", expected=ACTUATOR_ORDER, actual=actuator_names)

    home_ctrl = np.asarray(model.keyframe("home").ctrl, dtype=np.float32)
    if home_ctrl.shape != DEFAULT_ACTUATOR.shape or not np.allclose(home_ctrl, DEFAULT_ACTUATOR, atol=home_ctrl_atol, rtol=0.0):
        report.add("home_ctrl", "error", "MuJoCo home.ctrl differs from DEFAULT_ACTUATOR.", expected=DEFAULT_ACTUATOR.tolist(), actual=home_ctrl.tolist())

    ctrlrange = np.asarray(model.actuator_ctrlrange, dtype=np.float32)
    if ctrlrange.shape != ACTUATOR_CTRL_RANGES.shape or not np.allclose(ctrlrange, ACTUATOR_CTRL_RANGES, atol=ctrlrange_atol, rtol=0.0):
        report.add("actuator_ctrlrange", "error", "MuJoCo ctrl ranges differ from policy contract.", expected=ACTUATOR_CTRL_RANGES.tolist(), actual=ctrlrange.tolist())

    return report


def validate_control_cadence(model_timestep: float, decimation: int = DECIMATION) -> ValidationReport:
    report = ValidationReport("control_cadence")
    physics_rate_hz = 1.0 / float(model_timestep)
    policy_rate_hz = physics_rate_hz / int(decimation)

    if not np.isclose(model_timestep, SIM_DT, atol=1e-12, rtol=0.0):
        report.add("sim_timestep", "error", "MuJoCo timestep differs from policy contract.", expected=SIM_DT, actual=float(model_timestep))
    if int(decimation) != DECIMATION:
        report.add("decimation", "error", "Control decimation differs from policy contract.", expected=DECIMATION, actual=int(decimation))
    if not np.isclose(physics_rate_hz, EXPECTED_PHYSICS_RATE_HZ, atol=1e-9, rtol=0.0):
        report.add("physics_rate_hz", "error", "Physics rate differs from expected 500 Hz.", expected=EXPECTED_PHYSICS_RATE_HZ, actual=physics_rate_hz)
    if not np.isclose(policy_rate_hz, EXPECTED_POLICY_RATE_HZ, atol=1e-9, rtol=0.0):
        report.add("policy_rate_hz", "error", "Policy rate differs from expected 50 Hz.", expected=EXPECTED_POLICY_RATE_HZ, actual=policy_rate_hz)

    return report


def _read_assignment_float(text: str, name: str) -> float | None:
    match = re.search(rf"\b(?:self\.)?{re.escape(name)}\s*=\s*([-+]?\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def validate_upstream_reference(open_duck_root: str | Path) -> ValidationReport:
    report = ValidationReport("upstream_reference_constants")
    root = Path(open_duck_root)
    infer_path = root / "playground" / "open_duck_mini_v2" / "mujoco_infer.py"
    base_path = root / "playground" / "open_duck_mini_v2" / "mujoco_infer_base.py"

    try:
        infer_text = infer_path.read_text()
        base_text = base_path.read_text()
    except OSError as exc:
        report.add("upstream_files", "error", "Cannot read vendored Open Duck Playground inference files.", actual=str(exc))
        return report

    expected = {
        "action_scale": ACTION_SCALE,
        "dof_vel_scale": DOF_VEL_SCALE,
        "sim_dt": SIM_DT,
        "decimation": float(DECIMATION),
    }
    actual = {
        "action_scale": _read_assignment_float(infer_text, "action_scale"),
        "dof_vel_scale": _read_assignment_float(infer_text, "dof_vel_scale"),
        "sim_dt": _read_assignment_float(base_text, "sim_dt"),
        "decimation": _read_assignment_float(base_text, "decimation"),
    }

    for key, expected_value in expected.items():
        actual_value = actual[key]
        if actual_value is None:
            report.add(f"upstream_{key}", "warning", f"Could not find upstream {key} assignment.", expected=expected_value)
        elif not np.isclose(actual_value, expected_value, atol=1e-12, rtol=0.0):
            report.add(f"upstream_{key}", "error", f"Local {key} differs from vendored upstream.", expected=expected_value, actual=actual_value)

    return report
