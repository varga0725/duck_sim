from types import SimpleNamespace

import numpy as np

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


def _run(mode: str):
    sim = FakeLegacySimulator()
    controller = LegacyDynamicsController(mode=mode)
    before_x = float(sim.data.qpos[0])
    before_yaw = float(sim._kinematic_yaw)

    controller.apply(sim)

    diagnostics = controller.snapshot()
    return sim, diagnostics, float(sim.data.qpos[0] - before_x), float(sim._kinematic_yaw - before_yaw)


def test_legacy_still_performs_xy_qpos_integration():
    sim, diagnostics, forward_displacement, yaw_displacement = _run("legacy")

    assert sim.data.qpos[0] == 0.25 * 0.002
    assert forward_displacement > 0.0
    assert yaw_displacement == 0.0
    assert diagnostics["qpos_xy_integration_count"] == 1
    assert diagnostics["qvel_xy_forcing_count"] == 1
    assert diagnostics["qpos_z_forcing_count"] == 1
    assert diagnostics["torso_quaternion_overwrite_count"] == 1
    assert diagnostics["qvel_roll_pitch_zeroing_count"] == 1


def test_hybrid_skips_only_xy_qpos_integration():
    sim, diagnostics, forward_displacement, yaw_displacement = _run("hybrid")

    assert sim.data.qpos[0] == 0.0
    assert sim.data.qpos[1] == 0.0
    assert forward_displacement == 0.0
    assert yaw_displacement == 0.0
    assert diagnostics["mode"] == "hybrid"
    assert diagnostics["qpos_xy_integration_count"] == 0

    assert sim.data.qpos[2] == 0.15
    assert tuple(sim.data.qpos[3:7]) == (1.0, 0.0, 0.0, 0.0)
    assert sim.data.qvel[0] == 0.25
    assert sim.data.qvel[1] == 0.0
    assert sim.data.qvel[2] == 0.0
    assert sim.data.qvel[3] == 0.0
    assert sim.data.qvel[4] == 0.0
    assert sim.data.qvel[5] == 0.0


def test_hybrid_still_records_required_diagnostics():
    _sim, diagnostics, _forward_displacement, _yaw_displacement = _run("hybrid")

    assert diagnostics["qpos_z_forcing_count"] == 1
    assert diagnostics["torso_quaternion_overwrite_count"] == 1
    assert diagnostics["qvel_xy_forcing_count"] == 1
    assert diagnostics["qvel_roll_pitch_zeroing_count"] == 1
    assert diagnostics["correction_magnitude_sum"] > 0.0
    assert diagnostics["correction_magnitude_max"] > 0.0
    assert diagnostics["contact_duty_factor"] == {"left": 1.0, "right": 0.0, "both": 0.0}
    assert diagnostics["last_roll_deg"] == 0.0
    assert diagnostics["last_pitch_deg"] == 0.0
    assert diagnostics["last_body_height_m"] == 0.15
    assert diagnostics["last_actuator_saturation"] == 0.75
    assert diagnostics["last_fall_reason"] is None


def test_dynamic_remains_mapped_to_legacy_behavior_for_phase2b():
    sim, diagnostics, forward_displacement, _yaw_displacement = _run("dynamic")

    assert sim.data.qpos[0] == 0.25 * 0.002
    assert forward_displacement > 0.0
    assert diagnostics["mode"] == "dynamic"
    assert diagnostics["qpos_xy_integration_count"] == 1


def test_phase2b_does_not_change_public_api_schemas():
    assert "dynamics" not in RobotState.model_json_schema()["properties"]
    assert "dynamics" not in CommandResponse.model_json_schema()["properties"]
    assert "dynamics_mode" not in HealthResponse.model_json_schema()["properties"]
