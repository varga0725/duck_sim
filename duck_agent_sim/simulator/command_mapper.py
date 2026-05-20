from duck_agent_sim.schemas import RobotCommand, ControlIntent

def map_command(cmd: RobotCommand) -> ControlIntent:
    """
    Translates a high-level RobotCommand into a low-level ControlIntent (velocities/yaw rate).
    Does not expose raw joints.
    """
    linear_x = 0.0
    linear_y = 0.0
    yaw = 0.0

    command_name = cmd.command
    speed = cmd.speed
    turn = cmd.turn

    if command_name == "walk_forward":
        linear_x = speed
        linear_y = 0.0
        yaw = turn

    elif command_name == "walk_backward":
        linear_x = -speed * 0.6
        linear_y = 0.0
        yaw = turn

    elif command_name == "turn_left":
        linear_x = speed * 0.2
        linear_y = 0.0
        # Ensure we always rotate left, turn factor defaults to >= 0.4 if turn value is low
        yaw = max(abs(turn), 0.4)

    elif command_name == "turn_right":
        linear_x = speed * 0.2
        linear_y = 0.0
        # Ensure we always rotate right
        yaw = -max(abs(turn), 0.4)

    elif command_name == "stop" or command_name == "reset" or command_name == "look_around":
        linear_x = 0.0
        linear_y = 0.0
        yaw = 0.0

    return ControlIntent(
        linear_x=linear_x,
        linear_y=linear_y,
        yaw=yaw
    )
