import pytest
from pydantic import ValidationError
from duck_agent_sim.schemas import RobotCommand, RobotState, SafetyConfig

def test_valid_robot_command():
    cmd = RobotCommand(
        command="walk_forward",
        speed=0.5,
        turn=0.2,
        duration_sec=3.0,
        safety=SafetyConfig(stop_on_fall=True, max_pitch_deg=25.0)
    )
    assert cmd.command == "walk_forward"
    assert cmd.speed == 0.5
    assert cmd.turn == 0.2
    assert cmd.duration_sec == 3.0
    assert cmd.safety.max_pitch_deg == 25.0

def test_invalid_command_name():
    with pytest.raises(ValidationError):
        # "jump_up" is not in CommandType literal
        RobotCommand(command="jump_up")

def test_invalid_speed_limit():
    with pytest.raises(ValidationError):
        # ge=0.0, le=1.0. Speed 1.5 is out of bounds.
        RobotCommand(command="walk_forward", speed=1.5)

def test_invalid_turn_limit():
    with pytest.raises(ValidationError):
        # ge=-1.0, le=1.0. Turn -2.0 is out of bounds.
        RobotCommand(command="walk_forward", turn=-2.0)

def test_invalid_duration_limit():
    with pytest.raises(ValidationError):
        # ge=0.1, le=10.0. Duration 0.05 is too short.
        RobotCommand(command="walk_forward", duration_sec=0.05)

def test_robot_state_defaults():
    state = RobotState()
    assert state.robot == "open_duck_mini_v2"
    assert state.status == "idle"
    assert state.sim_time == 0.0
    assert state.position == (0.0, 0.0, 0.41)
    assert state.orientation.roll_deg == 0.0
    assert state.fallen is False
