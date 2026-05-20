import asyncio
import os
import sys

# Ensure fastmcp is installed or explain dependencies
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Fallback to a mock or raise an instructional error
    print("Error: 'mcp' library not found. Please install it using: pip install mcp fastmcp", file=sys.stderr)
    # We will still define the server structure for easy deployment
    class FastMCP:
        def __init__(self, name):
            self.name = name
        def tool(self):
            return lambda func: func

from duck_agent_sim.agent.hermes_client import HermesRobotClient
from duck_agent_sim.schemas import FollowerConfigSchema

# Initialize FastMCP Server
mcp = FastMCP("DuckRobotControl")

# Instantiate our asynchronous SDK client
# Reads base url from environment or defaults to local bridge
BRIDGE_URL = os.getenv("DUCK_BRIDGE_URL", "http://127.0.0.1:8765")
client = HermesRobotClient(base_url=BRIDGE_URL)


@mcp.tool()
async def get_robot_state() -> str:
    """
    Retrieves the current high-level RobotState from the simulator.
    Includes XYZ position coordinates, Roll/Pitch/Yaw Euler angles, feet contacts,
    fallen/stability status, and last executed command.
    """
    try:
        state = await client.get_state()
        return state.model_dump_json(indent=2)
    except Exception as e:
        return f"Error fetching robot state: {e}"


@mcp.tool()
async def get_sensors_state() -> str:
    """
    Retrieves the raw simulator sensor channels.
    Exposes raw IMU (accelerometer, gyro, local/global velocities, quaternions)
    and foot-level touch force/velocity sensors with explicit availability markers.
    """
    try:
        sensors = await client.get_sensors_state()
        return sensors.model_dump_json(indent=2)
    except Exception as e:
        return f"Error fetching sensor state: {e}"


@mcp.tool()
async def move_robot(
    command: str,
    speed: float = 0.25,
    turn: float = 0.0,
    duration_sec: float = 1.0
) -> str:
    """
    Sends a high-level motion command to the robot.
    
    Parameters:
      - command: One of: 'walk_forward', 'walk_backward', 'turn_left', 'turn_right', 'stop', 'reset', 'look_around'.
      - speed: Target linear speed factor (0.0 to 1.0, default 0.25).
      - turn: Pivot/yaw rate factor (-1.0 to 1.0, default 0.0).
      - duration_sec: Execution duration in seconds (0.1 to 10.0, default 1.0).
    """
    try:
        response = await client.send_command(
            command=command,
            speed=speed,
            turn=turn,
            duration_sec=duration_sec
        )
        return response.model_dump_json(indent=2)
    except Exception as e:
        return f"Error executing command '{command}': {e}"


@mcp.tool()
async def stop_robot() -> str:
    """Immediately halts all robot movement and stabilizers."""
    try:
        state = await client.stop()
        return f"Robot halted. Current status: {state.status}"
    except Exception as e:
        return f"Error stopping robot: {e}"


@mcp.tool()
async def reset_robot() -> str:
    """Resets the robot coordinates to the origin and recovers from any fallen or unstable states."""
    try:
        state = await client.reset()
        return f"Robot reset successful. Current status: {state.status}"
    except Exception as e:
        return f"Error resetting robot: {e}"


@mcp.tool()
async def get_vision_detections() -> str:
    """
    Retrieves the latest structured 2D bounding box detections from the active camera (YOLO).
    Returns object labels, confidence scores, pixel coordinates, and persistent tracking IDs.
    """
    try:
        detections = await client.get_vision_detections()
        import json
        return json.dumps(detections, indent=2)
    except Exception as e:
        return f"Error fetching vision detections: {e}"


@mcp.tool()
async def follow_target(
    target_label: str = "chair",
    follow_height: float = 380.0
) -> str:
    """
    Commands the robot to actively search for and walk toward a visual target.
    Uses continuous projected 3D tracking. Adjust 'follow_height' to walk closer (e.g. 380.0+).
    """
    try:
        config = FollowerConfigSchema(
            target_label=target_label,
            follow_height=follow_height
        )
        res = await client.start_following(config)
        import json
        return json.dumps(res, indent=2)
    except Exception as e:
        return f"Error starting follower: {e}"


@mcp.tool()
async def stop_following() -> str:
    """Stops the active visual target follower and halts the robot base."""
    try:
        res = await client.stop_following()
        import json
        return json.dumps(res, indent=2)
    except Exception as e:
        return f"Error stopping follower: {e}"


if __name__ == "__main__":
    # If run directly, launch the fastmcp server (uses stdio transport by default)
    if "FastMCP" in globals() and hasattr(mcp, "run"):
        mcp.run()
    else:
        print("MCP Server ready. Launch with FastMCP CLI or correct environment.", file=sys.stderr)
