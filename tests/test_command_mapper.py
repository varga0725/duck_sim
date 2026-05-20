from duck_agent_sim.schemas import RobotCommand, SafetyConfig
from duck_agent_sim.simulator.command_mapper import map_command

def test_walk_forward_mapping():
    cmd = RobotCommand(command="walk_forward", speed=0.5, turn=0.1)
    control = map_command(cmd)
    assert control.linear_x == 0.5
    assert control.linear_y == 0.0
    assert control.yaw == 0.1

def test_walk_backward_mapping():
    cmd = RobotCommand(command="walk_backward", speed=0.5, turn=-0.2)
    control = map_command(cmd)
    assert control.linear_x == -0.3  # -speed * 0.6
    assert control.linear_y == 0.0
    assert control.yaw == -0.2

def test_turn_left_mapping():
    cmd = RobotCommand(command="turn_left", speed=0.3, turn=0.1)
    control = map_command(cmd)
    assert control.linear_x == 0.06  # speed * 0.2
    assert control.yaw >= 0.4  # max(abs(turn), 0.4)

def test_turn_right_mapping():
    cmd = RobotCommand(command="turn_right", speed=0.3, turn=0.1)
    control = map_command(cmd)
    assert control.linear_x == 0.06  # speed * 0.2
    assert control.yaw <= -0.4  # -max(abs(turn), 0.4)

def test_stop_mapping():
    cmd = RobotCommand(command="stop")
    control = map_command(cmd)
    assert control.linear_x == 0.0
    assert control.yaw == 0.0

def test_reset_and_look_around_mapping():
    cmd1 = RobotCommand(command="reset")
    cmd2 = RobotCommand(command="look_around")
    control1 = map_command(cmd1)
    control2 = map_command(cmd2)
    assert control1.linear_x == 0.0
    assert control2.linear_x == 0.0
