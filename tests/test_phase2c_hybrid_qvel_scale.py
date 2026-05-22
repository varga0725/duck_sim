from types import SimpleNamespace

import numpy as np

from duck_agent_sim.config import DUCK_HYBRID_QVEL_XY_SCALE, parse_hybrid_qvel_xy_scale
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


def _run(mode: str, scale: float = 1.0):
    sim = FakeLegacySimulator()
    controller = LegacyDynamicsController(mode=mode, hybrid_qvel_xy_scale=scale)
    before_x = float(sim.data.qpos[0])

    controller.apply(sim)

    return sim, controller.snapshot(), float(sim.data.qpos[0] - before_x)


def test_default_hybrid_qvel_xy_scale_is_one():
    assert DUCK_HYBRID_QVEL_XY_SCALE == 1.0
    assert parse_hybrid_qvel_xy_scale(None) == 1.0


def test_invalid_hybrid_qvel_xy_scale_falls_back_to_one():
    assert parse_hybrid_qvel_xy_scale("") == 1.0
    assert parse_hybrid_qvel_xy_scale("bad") == 1.0
    assert parse_hybrid_qvel_xy_scale("-1.0") == 1.0
    assert parse_hybrid_qvel_xy_scale("0.25") == 1.0
    assert parse_hybrid_qvel_xy_scale("2.0") == 1.0


def test_supported_hybrid_qvel_xy_scale_values():
    assert parse_hybrid_qvel_xy_scale("1.0") == 1.0
    assert parse_hybrid_qvel_xy_scale("0.5") == 0.5
    assert parse_hybrid_qvel_xy_scale("0.0") == 0.0


def test_scale_affects_only_hybrid_mode():
    legacy, legacy_diag, legacy_forward = _run("legacy", scale=0.0)
    dynamic, dynamic_diag, dynamic_forward = _run("dynamic", scale=0.0)
    hybrid, hybrid_diag, hybrid_forward = _run("hybrid", scale=0.0)

    assert legacy.data.qvel[0] == 0.25
    assert legacy_forward > 0.0
    assert legacy_diag["qvel_xy_forcing_count"] == 1

    assert dynamic.data.qvel[0] == 0.25
    assert dynamic_forward > 0.0
    assert dynamic_diag["qvel_xy_forcing_count"] == 1

    assert hybrid.data.qvel[0] == 0.0
    assert hybrid_forward == 0.0
    assert hybrid_diag["qvel_xy_forcing_count"] == 0


def test_hybrid_qpos_xy_integration_remains_disabled():
    sim, diagnostics, forward_displacement = _run("hybrid", scale=0.5)

    assert sim.data.qpos[0] == 0.0
    assert sim.data.qpos[1] == 0.0
    assert forward_displacement == 0.0
    assert diagnostics["qpos_xy_integration_count"] == 0


def test_scale_one_preserves_phase2b_hybrid_behavior():
    sim, diagnostics, forward_displacement = _run("hybrid", scale=1.0)

    assert sim.data.qpos[0] == 0.0
    assert forward_displacement == 0.0
    assert sim.data.qvel[0] == 0.25
    assert sim.data.qvel[1] == 0.0
    assert diagnostics["qvel_xy_forcing_count"] == 1
    assert diagnostics["last_qvel_xy_commanded_magnitude"] == 0.25


def test_scale_half_reduces_hybrid_qvel_xy_forcing():
    sim, diagnostics, forward_displacement = _run("hybrid", scale=0.5)

    assert sim.data.qpos[0] == 0.0
    assert forward_displacement == 0.0
    assert sim.data.qvel[0] == 0.125
    assert sim.data.qvel[1] == 0.0
    assert diagnostics["qvel_xy_forcing_count"] == 1
    assert diagnostics["last_qvel_xy_commanded_magnitude"] == 0.125


def test_scale_zero_disables_hybrid_qvel_xy_forcing():
    sim, diagnostics, forward_displacement = _run("hybrid", scale=0.0)

    assert sim.data.qpos[0] == 0.0
    assert forward_displacement == 0.0
    assert sim.data.qvel[0] == 0.0
    assert sim.data.qvel[1] == 0.0
    assert diagnostics["qvel_xy_forcing_count"] == 0
    assert diagnostics["last_qvel_xy_commanded_magnitude"] == 0.0


def test_phase2c_does_not_change_public_api_schemas():
    assert "dynamics" not in RobotState.model_json_schema()["properties"]
    assert "dynamics_mode" not in CommandResponse.model_json_schema()["properties"]
    assert "hybrid_qvel_xy_scale" not in HealthResponse.model_json_schema()["properties"]
