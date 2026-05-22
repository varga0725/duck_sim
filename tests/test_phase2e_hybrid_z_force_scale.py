from types import SimpleNamespace

import numpy as np
import pytest

from duck_agent_sim.config import DUCK_HYBRID_Z_FORCE_SCALE, parse_hybrid_z_force_scale
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


def _run(mode: str, qvel_scale: float = 1.0, z_scale: float = 1.0):
    sim = FakeLegacySimulator()
    controller = LegacyDynamicsController(
        mode=mode,
        hybrid_qvel_xy_scale=qvel_scale,
        hybrid_z_force_scale=z_scale,
    )
    controller.apply(sim)
    return sim, controller.snapshot()


def test_default_hybrid_z_force_scale_is_one():
    assert DUCK_HYBRID_Z_FORCE_SCALE == 1.0
    assert parse_hybrid_z_force_scale(None) == 1.0


def test_invalid_hybrid_z_force_scale_falls_back_to_one():
    assert parse_hybrid_z_force_scale("") == 1.0
    assert parse_hybrid_z_force_scale("bad") == 1.0
    assert parse_hybrid_z_force_scale("-1.0") == 1.0
    assert parse_hybrid_z_force_scale("0.25") == 1.0
    assert parse_hybrid_z_force_scale("2.0") == 1.0


def test_supported_hybrid_z_force_scale_values():
    assert parse_hybrid_z_force_scale("1.0") == 1.0
    assert parse_hybrid_z_force_scale("0.5") == 0.5
    assert parse_hybrid_z_force_scale("0.0") == 0.0


def test_z_force_scale_affects_only_hybrid_mode():
    legacy, legacy_diag = _run("legacy", z_scale=0.0)
    dynamic, dynamic_diag = _run("dynamic", z_scale=0.0)
    hybrid, hybrid_diag = _run("hybrid", z_scale=0.0)

    assert legacy.data.qpos[2] == 0.15
    assert legacy_diag["qpos_z_forcing_count"] == 1
    assert dynamic.data.qpos[2] == 0.15
    assert dynamic_diag["qpos_z_forcing_count"] == 1

    assert hybrid.data.qpos[2] == 0.20
    assert hybrid.data.qvel[2] == -0.5
    assert hybrid_diag["qpos_z_forcing_count"] == 0


def test_hybrid_qpos_xy_integration_remains_disabled():
    sim, diagnostics = _run("hybrid", qvel_scale=0.0, z_scale=0.0)

    assert sim.data.qpos[0] == 0.0
    assert sim.data.qpos[1] == 0.0
    assert diagnostics["qpos_xy_integration_count"] == 0


def test_hybrid_qvel_scale_zero_remains_supported():
    sim, diagnostics = _run("hybrid", qvel_scale=0.0, z_scale=1.0)

    assert sim.data.qvel[0] == 0.0
    assert sim.data.qvel[1] == 0.0
    assert diagnostics["qvel_xy_forcing_count"] == 0
    assert diagnostics["last_qvel_xy_commanded_magnitude"] == 0.0


def test_hybrid_z_force_scale_one_preserves_current_behavior():
    sim, diagnostics = _run("hybrid", z_scale=1.0)

    assert sim.data.qpos[2] == 0.15
    assert sim.data.qvel[2] == 0.0
    assert diagnostics["qpos_z_forcing_count"] == 1
    assert diagnostics["qpos_z_correction_magnitude_sum"] == pytest.approx(0.05)
    assert diagnostics["qpos_z_correction_magnitude_max"] == pytest.approx(0.05)


def test_hybrid_z_force_scale_half_reduces_z_correction():
    sim, diagnostics = _run("hybrid", z_scale=0.5)

    assert sim.data.qpos[2] == 0.175
    assert sim.data.qvel[2] == 0.0
    assert diagnostics["qpos_z_forcing_count"] == 1
    assert diagnostics["qpos_z_correction_magnitude_sum"] == pytest.approx(0.025)
    assert diagnostics["qpos_z_correction_magnitude_max"] == pytest.approx(0.025)


def test_hybrid_z_force_scale_zero_disables_direct_z_forcing():
    sim, diagnostics = _run("hybrid", z_scale=0.0)

    assert sim.data.qpos[2] == 0.20
    assert sim.data.qvel[2] == -0.5
    assert diagnostics["qpos_z_forcing_count"] == 0
    assert diagnostics["qpos_z_correction_magnitude_sum"] == 0.0
    assert diagnostics["qpos_z_correction_magnitude_max"] == 0.0


def test_phase2e_does_not_change_public_api_schemas():
    assert "dynamics" not in RobotState.model_json_schema()["properties"]
    assert "dynamics_mode" not in CommandResponse.model_json_schema()["properties"]
    assert "hybrid_z_force_scale" not in HealthResponse.model_json_schema()["properties"]
