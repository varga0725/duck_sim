import asyncio
import os
from duck_agent_sim.agent.hermes_client import HermesRobotClient
from duck_agent_sim.schemas import FollowerConfigSchema

# Initialize client using environment variable or default
BRIDGE_URL = os.getenv("DUCK_BRIDGE_URL", "http://127.0.0.1:8765")
client = HermesRobotClient(base_url=BRIDGE_URL)

def register(ctx):
    """
    Registers the Duck Robot simulation control tools natively with the Hermes Agent context.
    """
    
    @ctx.tool(
        name="get_robot_state",
        description="Retrieves the current high-level RobotState from the simulator (XYZ, RPY, stability, contact state)."
    )
    async def get_robot_state() -> str:
        try:
            state = await client.get_state()
            return state.model_dump_json(indent=2)
        except Exception as e:
            return f"Error: {e}"

    @ctx.tool(
        name="get_sensors_state",
        description="Retrieves the raw 500Hz sensor channels (accelerometer, gyro, foot touch sensors)."
    )
    async def get_sensors_state() -> str:
        try:
            sensors = await client.get_sensors_state()
            return sensors.model_dump_json(indent=2)
        except Exception as e:
            return f"Error: {e}"

    @ctx.tool(
        name="move_robot",
        description="Sends a high-level motion command: 'walk_forward', 'walk_backward', 'turn_left', 'turn_right', 'stop', 'reset'."
    )
    async def move_robot(
        command: str,
        speed: float = 0.25,
        turn: float = 0.0,
        duration_sec: float = 1.0
    ) -> str:
        try:
            res = await client.send_command(
                command=command,
                speed=speed,
                turn=turn,
                duration_sec=duration_sec
            )
            return res.model_dump_json(indent=2)
        except Exception as e:
            return f"Error executing '{command}': {e}"

    @ctx.tool(
        name="get_vision_detections",
        description="Retrieves the latest structured 2D bounding box detections from the active camera (YOLO)."
    )
    async def get_vision_detections() -> str:
        try:
            detections = await client.get_vision_detections()
            import json
            return json.dumps(detections, indent=2)
        except Exception as e:
            return f"Error: {e}"

    @ctx.tool(
        name="follow_target",
        description="Commands the robot to actively search for and walk toward a visual target (e.g. 'chair')."
    )
    async def follow_target(
        target_label: str = "chair",
        follow_height: float = 380.0
    ) -> str:
        try:
            config = FollowerConfigSchema(
                target_label=target_label,
                follow_height=follow_height
            )
            res = await client.start_following(config)
            import json
            return json.dumps(res, indent=2)
        except Exception as e:
            return f"Error: {e}"

    @ctx.tool(
        name="stop_following",
        description="Stops the active visual target follower and halts the robot."
    )
    async def stop_following() -> str:
        try:
            res = await client.stop_following()
            import json
            return json.dumps(res, indent=2)
        except Exception as e:
            return f"Error: {e}"
