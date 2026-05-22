from types import SimpleNamespace

import numpy as np
import pytest

from duck_agent_sim.config import DUCK_HYBRID_TORSO_ORIENTATION_SCALE, parse_hybrid_torso_orientation_scale
from duck_agent_sim.schemas import CommandResponse, HealthResponse, RobotState
from duck_agent_sim.simulator.legacy_dynamics import LegacyDynamicsController


class FakeLegacySimulator:
    def __init__(self):
        self.data = SimpleNamespace(
            qpos=np.array([0.0, 0.0, 0.20, 1.0, 0.0, 0.0, 0.0], dtype=float),
            qvel=np.array([0.0, 0.0, -0.5, 1.0, -1.0, 0.0], dtype=float),
            ctrl=np.array([0.0, 0.5], dtype=float),
        )
        self.model = SimpleNamespace(
            actuator_ctrlrange=np.array([[-1.0, 1.0], [-1.0, 1.0]], dtype=float),
        )
        self._kinematic_yaw = 0.0
        self._current_linear_x = 0.25
        self._current_linear_y = 0.0
        self._current_yaw_rate = 0.0

    @staticmethod
    def quaternion_to_euler(qw, qx, qy, qz):
        return (3.0, 2.0, 0.0)

    @staticmethod
    def check_contact(body1_name, body2_name):
        return body1_name == "foot_assembly"


def _run(mode: str, torso_scale: float = 1.0):
    sim = FakeLegacySimulator()
    controller = LegacyDynamicsController(mode=mode, hybrid_torso_orientation_scale=torso_scale)
    before_quat = np.array(sim.data.qpos[3:7], copy=True)
    controller.apply(sim)
    return before_quat, sim, controller.snapshot()


def test_default_hybrid_torso_orientation_scale_is_one():
    assert DUCK_HYBRID_TORSO_ORIENTATION_SCALE == 1.0
    assert parse_hybrid_torso_orientation_scale(None) == 1.0


def test_invalid_hybrid_torso_orientation_scale_falls_back_to_one():
    assert parse_hybrid_torso_orientation_scale("") == 1.0
    assert parse_hybrid_torso_orientation_scale("bad") == 1.0
    assert parse_hybrid_torso_orientation_scale("-1.0") == 1.0
    assert parse_hybrid_torso_orientation_scale("0.25") == 1.0
    assert parse_hybrid_torso_orientation_scale("2.0") == 1.0


def test_supported_hybrid_torso_orientation_scale_values():
    assert parse_hybrid_torso_orientation_scale("1.0") == 1.0
    assert parse_hybrid_torso_orientation_scale("0.5") == 0.5
    assert parse_hybrid_torso_orientation_scale("0.0") == 0.0


def test_torso_orientation_scale_affects_only_hybrid_mode():
    legacy_before, legacy, legacy_diag = _run("legacy", torso_scale=0.0)
    dynamic_before, dynamic, dynamic_diag = _run("dynamic", torso_scale=0.0)
    hybrid_before, hybrid, hybrid_diag = _run("hybrid", torso_scale=0.0)

    assert not np.allclose(legacy.data.qpos[3:7], legacy_before)
    assert legacy_diag["torso_quaternion_overwrite_count"] == 1

    assert not np.allclose(dynamic.data.qpos[3:7], dynamic_before)
    assert dynamic_diag["torso_quaternion_overwrite_count"] == 1

    assert np.allclose(hybrid.data.qpos[3:7], hybrid_before)
    assert hybrid_diag["torso_quaternion_overwrite_count"] == 0


def test_scale_one_preserves_phase2f_hybrid_behavior():
    before_quat, sim, diagnostics = _run("hybrid", torso_scale=1.0)

    assert not np.allclose(sim.data.qpos[3:7], before_quat)
    assert diagnostics["torso_quaternion_overwrite_count"] == 1
    assert diagnostics["torso_orientation_correction_magnitude_sum"] > 0.0
    assert diagnostics["torso_orientation_correction_magnitude_max"] > 0.0


def test_scale_half_partially_corrects_hybrid_torso_orientation():
    before_full, full, full_diag = _run("hybrid", torso_scale=1.0)
    before_half, half, half_diag = _run("hybrid", torso_scale=0.5)

    full_delta = float(np.linalg.norm(full.data.qpos[3:7] - before_full))
    half_delta = float(np.linalg.norm(half.data.qpos[3:7] - before_half))

    assert half_delta > 0.0
    assert half_delta < full_delta
    assert half_diag["torso_quaternion_overwrite_count"] == 1
    assert half_diag["torso_orientation_correction_magnitude_sum"] == pytest.approx(
        full_diag["torso_orientation_correction_magnitude_sum"] * 0.5
    )


def test_scale_zero_disables_direct_torso_quaternion_overwrite_in_hybrid():
    before_quat, sim, diagnostics = _run("hybrid", torso_scale=0.0)

    assert np.allclose(sim.data.qpos[3:7], before_quat)
    assert diagnostics["torso_quaternion_overwrite_count"] == 0
    assert diagnostics["torso_orientation_correction_magnitude_sum"] == 0.0
    assert diagnostics["torso_orientation_correction_magnitude_max"] == 0.0


def test_phase2g_does_not_change_public_api_schemas():
    assert "dynamics" not in RobotState.model_json_schema()["properties"]
    assert "dynamics_mode" not in CommandResponse.model_json_schema()["properties"]
    assert "hybrid_torso_orientation_scale" not in HealthResponse.model_json_schema()["properties"]
