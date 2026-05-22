import logging
import threading

import pytest

from duck_agent_sim.schemas import ControlIntent, RobotState, SafetyConfig
from duck_agent_sim.simulator import duck_sim
from duck_agent_sim.simulator.control_plane import DesiredMotionState
from duck_agent_sim.simulator.duck_sim import MockDuckSimulator, RealDuckSimulator
from duck_agent_sim.simulator.policy_contract import POLICY_COMMAND_LIMITS
from duck_agent_sim.simulator.policy_contract_validator import ValidationReport


def test_mock_set_desired_control_clamps_direct_policy_command_limits():
    sim = MockDuckSimulator.__new__(MockDuckSimulator)
    sim._intent_lock = threading.RLock()
    sim._state = RobotState()
    sim.get_state = lambda: sim._state

    sim.set_desired_control(
        ControlIntent(linear_x=0.3, linear_y=-0.9, yaw=3.0),
        SafetyConfig(),
        command="vision_follow",
    )

    assert isinstance(sim._desired_motion, DesiredMotionState)
    assert sim._desired_motion.control.linear_x == POLICY_COMMAND_LIMITS.linear_x[1]
    assert sim._desired_motion.control.linear_y == POLICY_COMMAND_LIMITS.linear_y[0]
    assert sim._desired_motion.control.yaw == POLICY_COMMAND_LIMITS.yaw[1]
    assert sim._state.last_command == "vision_follow"


def test_real_set_desired_control_clamps_direct_policy_command_limits():
    sim = RealDuckSimulator.__new__(RealDuckSimulator)
    sim._lock = threading.RLock()
    sim._initialize_mujoco = lambda: None
    sim.get_state = lambda: RobotState()

    sim.set_desired_control(
        ControlIntent(linear_x=0.3, linear_y=-0.9, yaw=3.0),
        SafetyConfig(),
        command="vision_follow",
    )

    assert sim._target_linear_x == POLICY_COMMAND_LIMITS.linear_x[1]
    assert sim._target_linear_y == POLICY_COMMAND_LIMITS.linear_y[0]
    assert sim._target_yaw_rate == POLICY_COMMAND_LIMITS.yaw[1]
    assert sim._last_command == "vision_follow"


def test_real_step_clamps_direct_policy_command_limits():
    sim = RealDuckSimulator.__new__(RealDuckSimulator)
    sim._initialize_mujoco = lambda: None
    sim.get_state = lambda: RobotState()

    sim.step(ControlIntent(linear_x=-0.3, linear_y=0.9, yaw=-3.0), 0.1, SafetyConfig())

    assert sim._target_linear_x == POLICY_COMMAND_LIMITS.linear_x[0]
    assert sim._target_linear_y == POLICY_COMMAND_LIMITS.linear_y[1]
    assert sim._target_yaw_rate == POLICY_COMMAND_LIMITS.yaw[0]


def test_policy_contract_startup_validation_is_warning_only(monkeypatch, caplog):
    sim = RealDuckSimulator.__new__(RealDuckSimulator)
    sim.model = object()
    sim._onnx_session = None

    def fail_validation(_model):
        raise RuntimeError("validator unavailable")

    monkeypatch.setattr(duck_sim, "validate_mujoco_model", fail_validation)

    with caplog.at_level(logging.WARNING, logger="duck-agent-sim"):
        sim._validate_policy_contract_warnings()

    assert "Policy contract validation warning pass failed" in caplog.text


def test_policy_contract_startup_validation_logs_issues_without_failing(caplog):
    report = ValidationReport("test_report")
    report.add(
        "test_check",
        "warning",
        "synthetic mismatch",
        expected="expected",
        actual="actual",
    )

    with caplog.at_level(logging.WARNING, logger="duck-agent-sim"):
        duck_sim._log_policy_validation_report(report)

    assert "synthetic mismatch" in caplog.text
    assert "expected='expected'" in caplog.text
