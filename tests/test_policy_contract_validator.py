import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from duck_agent_sim.config import DUCK_ONNX_MODEL_PATH
from duck_agent_sim.schemas import RobotCommand
from duck_agent_sim.simulator.command_mapper import map_command
from duck_agent_sim.simulator.policy_contract import (
    OBSERVATION_SIZE,
    POLICY_COMMAND_LIMITS,
)
from duck_agent_sim.simulator.policy_contract_validator import (
    COMMAND_SLICE,
    validate_command_values,
    validate_control_cadence,
    validate_mujoco_model,
    validate_observation,
    validate_onnx_model,
    validate_upstream_reference,
)


def _issue_codes(report):
    return {issue.check for issue in report.issues}


def test_bundled_onnx_model_matches_policy_contract():
    report = validate_onnx_model(DUCK_ONNX_MODEL_PATH)

    assert report.ok
    assert report.issues == []


def test_observation_validation_accepts_valid_float32_vector():
    obs = np.zeros(OBSERVATION_SIZE, dtype=np.float32)
    obs[COMMAND_SLICE] = np.array([0.15, -0.2, 1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)

    report = validate_observation(obs)

    assert report.ok
    assert report.issues == []


@pytest.mark.parametrize(
    ("obs", "expected_check"),
    [
        (np.zeros(OBSERVATION_SIZE + 1, dtype=np.float32), "observation_shape"),
        (np.zeros(OBSERVATION_SIZE, dtype=np.float64), "observation_dtype"),
    ],
)
def test_observation_validation_rejects_shape_and_dtype_drift(obs, expected_check):
    report = validate_observation(obs)

    assert not report.ok
    assert expected_check in _issue_codes(report)


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_observation_validation_rejects_non_finite_values(bad_value):
    obs = np.zeros(OBSERVATION_SIZE, dtype=np.float32)
    obs[0] = bad_value

    report = validate_observation(obs)

    assert not report.ok
    assert "observation_finite" in _issue_codes(report)


def test_observation_validation_rejects_out_of_range_command_slice():
    obs = np.zeros(OBSERVATION_SIZE, dtype=np.float32)
    obs[COMMAND_SLICE] = np.array([0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)

    report = validate_observation(obs)

    assert not report.ok
    assert "command_linear_x_range" in _issue_codes(report)


def test_control_cadence_validation_matches_phase3a_contract():
    report = validate_control_cadence(model_timestep=0.002, decimation=10)

    assert report.ok
    assert report.issues == []


def test_control_cadence_validation_reports_drift():
    report = validate_control_cadence(model_timestep=0.001, decimation=5)

    assert not report.ok
    assert {"sim_timestep", "decimation", "physics_rate_hz", "policy_rate_hz"} <= _issue_codes(report)


def test_rest_command_mapping_remains_clamped_to_policy_limits():
    control = map_command(RobotCommand(command="walk_forward", speed=1.0, turn=1.0))
    report = validate_command_values(control.linear_x, control.linear_y, control.yaw)

    assert report.ok
    assert control.linear_x == POLICY_COMMAND_LIMITS.linear_x[1]
    assert control.yaw == POLICY_COMMAND_LIMITS.yaw[1]


def test_follower_default_speed_can_exceed_policy_linear_x_limit_and_is_reported():
    report = validate_command_values(linear_x=0.3, linear_y=0.0, yaw=0.0)

    assert not report.ok
    assert "command_linear_x_range" in _issue_codes(report)


def test_vendored_upstream_constants_match_local_policy_contract():
    root = Path(__file__).resolve().parents[1] / "external" / "Open_Duck_Playground"
    report = validate_upstream_reference(root)

    assert report.ok
    assert report.issues == []


@pytest.mark.skipif(
    importlib.util.find_spec("mujoco") is None,
    reason="MuJoCo is optional in unit-test environments",
)
def test_mujoco_model_matches_policy_actuator_contract():
    import mujoco

    pytest.importorskip("mujoco_playground")

    external_path = Path(__file__).resolve().parents[1] / "external" / "Open_Duck_Playground"
    if str(external_path) not in sys.path:
        sys.path.append(str(external_path))

    from playground.open_duck_mini_v2 import base
    from playground.open_duck_mini_v2.constants import FLAT_TERRAIN_XML

    xml_text = base.epath.Path(FLAT_TERRAIN_XML).read_text()
    model = mujoco.MjModel.from_xml_string(xml_text, assets=base.get_assets())
    model.opt.timestep = 0.002

    model_report = validate_mujoco_model(model)
    cadence_report = validate_control_cadence(model.opt.timestep, decimation=10)

    assert model_report.ok
    assert model_report.issues == []
    assert cadence_report.ok
    assert cadence_report.issues == []
