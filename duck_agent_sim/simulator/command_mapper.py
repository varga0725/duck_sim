from duck_agent_sim.schemas import ControlIntent, RobotCommand
from duck_agent_sim.simulator.policy_contract import clamp_control_to_policy_limits


def map_command(cmd: RobotCommand) -> ControlIntent:
    """
    Translates a high-level RobotCommand into a conservative policy command.

    The public API accepts normalized speed/turn values, but the ONNX walking
    policy was deployed with a much narrower command distribution. Clamp the
    mapped velocity/yaw command before it reaches the observation vector.
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
        # Ensure we rotate left even when turn input is small.
        yaw = max(abs(turn), 0.4)

    elif command_name == "turn_right":
        linear_x = speed * 0.2
        linear_y = 0.0
        # Ensure we always rotate right
        yaw = -max(abs(turn), 0.4)

    elif command_name in {"stop", "reset", "look_around"}:
        linear_x = 0.0
        linear_y = 0.0
        yaw = 0.0

    clamped = clamp_control_to_policy_limits(linear_x, linear_y, yaw)
    return ControlIntent(
        linear_x=clamped.linear_x,
        linear_y=clamped.linear_y,
        yaw=clamped.yaw,
    )
