from types import SimpleNamespace

import numpy as np
import pytest

from duck_agent_sim.config import DUCK_HYBRID_RP_QVEL_ZERO_SCALE, parse_hybrid_rp_qvel_zero_scale
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
        return (0.0, 0.0, 0.0)

    @staticmethod
    def check_contact(body1_name, body2_name):
        return body1_name == "foot_assembly"


def _run(mode: str, rp_scale: float = 1.0):
    sim = FakeLegacySimulator()
    controller = LegacyDynamicsController(mode=mode, hybrid_rp_qvel_zero_scale=rp_scale)
    controller.apply(sim)
    return sim, controller.snapshot()


def test_default_hybrid_rp_qvel_zero_scale_is_one():
    assert DUCK_HYBRID_RP_QVEL_ZERO_SCALE == 1.0
    assert parse_hybrid_rp_qvel_zero_scale(None) == 1.0


def test_invalid_hybrid_rp_qvel_zero_scale_falls_back_to_one():
    assert parse_hybrid_rp_qvel_zero_scale("") == 1.0
    assert parse_hybrid_rp_qvel_zero_scale("bad") == 1.0
    assert parse_hybrid_rp_qvel_zero_scale("-1.0") == 1.0
    assert parse_hybrid_rp_qvel_zero_scale("0.25") == 1.0
    assert parse_hybrid_rp_qvel_zero_scale("2.0") == 1.0


def test_supported_hybrid_rp_qvel_zero_scale_values():
    assert parse_hybrid_rp_qvel_zero_scale("1.0") == 1.0
    assert parse_hybrid_rp_qvel_zero_scale("0.5") == 0.5
    assert parse_hybrid_rp_qvel_zero_scale("0.0") == 0.0


def test_rp_qvel_zero_scale_affects_only_hybrid_mode():
    legacy, legacy_diag = _run("legacy", rp_scale=0.0)
    dynamic, dynamic_diag = _run("dynamic", rp_scale=0.0)
    hybrid, hybrid_diag = _run("hybrid", rp_scale=0.0)

    assert legacy.data.qvel[3] == 0.0
    assert legacy.data.qvel[4] == 0.0
    assert legacy_diag["qvel_roll_pitch_zeroing_count"] == 1

    assert dynamic.data.qvel[3] == 0.0
    assert dynamic.data.qvel[4] == 0.0
    assert dynamic_diag["qvel_roll_pitch_zeroing_count"] == 1

    assert hybrid.data.qvel[3] == 1.0
    assert hybrid.data.qvel[4] == -1.0
    assert hybrid_diag["qvel_roll_pitch_zeroing_count"] == 0


def test_scale_one_preserves_phase2e_hybrid_behavior():
    sim, diagnostics = _run("hybrid", rp_scale=1.0)

    assert sim.data.qvel[3] == 0.0
    assert sim.data.qvel[4] == 0.0
    assert diagnostics["qvel_roll_pitch_zeroing_count"] == 1
    assert diagnostics["qvel_roll_pitch_damping_magnitude_sum"] == pytest.approx(2 ** 0.5)
    assert diagnostics["qvel_roll_pitch_damping_magnitude_max"] == pytest.approx(2 ** 0.5)


def test_scale_half_partially_damps_hybrid_roll_pitch_qvel():
    sim, diagnostics = _run("hybrid", rp_scale=0.5)

    assert sim.data.qvel[3] == 0.5
    assert sim.data.qvel[4] == -0.5
    assert diagnostics["qvel_roll_pitch_zeroing_count"] == 1
    assert diagnostics["qvel_roll_pitch_damping_magnitude_sum"] == pytest.approx((2 ** 0.5) * 0.5)


def test_scale_zero_disables_direct_roll_pitch_qvel_zeroing_in_hybrid():
    sim, diagnostics = _run("hybrid", rp_scale=0.0)

    assert sim.data.qvel[3] == 1.0
    assert sim.data.qvel[4] == -1.0
    assert diagnostics["qvel_roll_pitch_zeroing_count"] == 0
    assert diagnostics["qvel_roll_pitch_damping_magnitude_sum"] == 0.0
    assert diagnostics["qvel_roll_pitch_damping_magnitude_max"] == 0.0


def test_phase2f_does_not_change_public_api_schemas():
    assert "dynamics" not in RobotState.model_json_schema()["properties"]
    assert "dynamics_mode" not in CommandResponse.model_json_schema()["properties"]
    assert "hybrid_rp_qvel_zero_scale" not in HealthResponse.model_json_schema()["properties"]
