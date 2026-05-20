from typing import Dict, Any, List
from duck_agent_sim.schemas import RobotCommand, RobotState

# Standard system/role instructions for LLM Agents controlling the duck
SYSTEM_INSTRUCTION = (
    "You are the Duck Robot Control Agent. You control a virtual Open Duck Mini v2 robot "
    "in MuJoCo simulation. You may only issue high-level commands through the Duck Agent "
    "Bridge API. You must never output raw joint angles or motor commands. Always "
    "inspect robot state before issuing a new command. If fallen or unstable, stop and reset."
)

def build_agent_context(state: RobotState) -> Dict[str, Any]:
    """
    Transforms the current RobotState into an LLM-friendly context dictionary
    focusing on stability, position, and last command.
    """
    return {
        "robot_type": state.robot,
        "status": state.status,
        "sim_time_sec": round(state.sim_time, 2),
        "position_xyz": [round(c, 3) for c in state.position],
        "orientation_roll_pitch_yaw_deg": {
            "roll": round(state.orientation.roll_deg, 1),
            "pitch": round(state.orientation.pitch_deg, 1),
            "yaw": round(state.orientation.yaw_deg, 1),
        },
        "feet_floor_contact": {
            "left": state.feet_contact.left,
            "right": state.feet_contact.right,
        },
        "is_fallen": state.fallen,
        "last_command_executed": state.last_command,
        "stability_alert": "CRITICAL - ROBOT IS FALLEN" if state.fallen else "STABLE"
    }

def build_allowed_commands() -> List[Dict[str, Any]]:
    """
    Returns a schema structure that defines allowed high-level commands and parameters
    for LLM tool use.
    """
    return [
        {
            "name": "walk_forward",
            "description": "Walks the duck forward.",
            "parameters": {
                "speed": "Float (0.0 to 1.0, default 0.25)",
                "turn": "Yaw rate adjustment (-1.0 to 1.0, default 0.0)",
                "duration_sec": "Float (0.1 to 10.0, default 1.0)"
            }
        },
        {
            "name": "walk_backward",
            "description": "Walks the duck backward at a reduced speed safety factor.",
            "parameters": {
                "speed": "Float (0.0 to 1.0, default 0.25)",
                "turn": "Yaw rate adjustment (-1.0 to 1.0, default 0.0)",
                "duration_sec": "Float (0.1 to 10.0, default 1.0)"
            }
        },
        {
            "name": "turn_left",
            "description": "Rotates the duck counter-clockwise on the spot.",
            "parameters": {
                "speed": "Speed of pivot (default 0.25)",
                "turn": "Pivot rate factor (0.0 to 1.0, default 0.4)",
                "duration_sec": "Float (0.1 to 10.0, default 1.0)"
            }
        },
        {
            "name": "turn_right",
            "description": "Rotates the duck clockwise on the spot.",
            "parameters": {
                "speed": "Speed of pivot (default 0.25)",
                "turn": "Pivot rate factor (0.0 to 1.0, default 0.4)",
                "duration_sec": "Float (0.1 to 10.0, default 1.0)"
            }
        },
        {
            "name": "stop",
            "description": "Immediately halts all movement and stabilizers.",
            "parameters": {}
        },
        {
            "name": "reset",
            "description": "Resets simulation parameters and recovers coordinates to origin.",
            "parameters": {}
        },
        {
            "name": "look_around",
            "description": "Duck looks around without changing base XY position coordinates.",
            "parameters": {
                "duration_sec": "Float (default 1.0)"
            }
        }
    ]

def validate_agent_command(payload: Dict[str, Any]) -> RobotCommand:
    """
    Parses and validates LLM output JSON payload into a strictly-validated RobotCommand.
    Raises ValidationError if invalid.
    """
    return RobotCommand(**payload)
