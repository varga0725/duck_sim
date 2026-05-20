import asyncio
import os
import sys
from pathlib import Path

# Add project workspace directory to sys.path to enable loading of duck_agent_sim
workspace_dir = "/Users/vargaferenc/Desktop/duck_sim"
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from duck_agent_sim.agent.hermes_client import HermesRobotClient
from duck_agent_sim.schemas import FollowerConfigSchema

# Initialize client using environment variable or default
BRIDGE_URL = os.getenv("DUCK_BRIDGE_URL", "http://127.0.0.1:8765")
client = HermesRobotClient(base_url=BRIDGE_URL)

def register(ctx):
    """
    Registers the Duck Robot simulation control tools natively with the Hermes Agent context.
    Provides tight multi-modal integration: see, hear, speak.
    """
    
    # 1. get_robot_state
    async def get_robot_state_handler(args, **kwargs) -> str:
        try:
            state = await client.get_state()
            return state.model_dump_json(indent=2)
        except Exception as e:
            return f"Error: {e}"

    ctx.register_tool(
        name="get_robot_state",
        toolset="duck-robot",
        schema={
            "name": "get_robot_state",
            "description": "Retrieves the current high-level RobotState from the simulator (XYZ, RPY, stability, contact state).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        handler=get_robot_state_handler,
        is_async=True,
        description="Retrieves the current high-level RobotState from the simulator (XYZ, RPY, stability, contact state)."
    )

    # 2. get_sensors_state
    async def get_sensors_state_handler(args, **kwargs) -> str:
        try:
            sensors = await client.get_sensors_state()
            return sensors.model_dump_json(indent=2)
        except Exception as e:
            return f"Error: {e}"

    ctx.register_tool(
        name="get_sensors_state",
        toolset="duck-robot",
        schema={
            "name": "get_sensors_state",
            "description": "Retrieves the raw 500Hz sensor channels (accelerometer, gyro, foot touch sensors).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        handler=get_sensors_state_handler,
        is_async=True,
        description="Retrieves the raw 500Hz sensor channels (accelerometer, gyro, foot touch sensors)."
    )

    # 3. move_robot
    async def move_robot_handler(args, **kwargs) -> str:
        command = args.get("command")
        speed = args.get("speed", 0.25)
        turn = args.get("turn", 0.0)
        duration_sec = args.get("duration_sec", 1.0)
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

    ctx.register_tool(
        name="move_robot",
        toolset="duck-robot",
        schema={
            "name": "move_robot",
            "description": "Sends a high-level motion command: 'walk_forward', 'walk_backward', 'turn_left', 'turn_right', 'stop', 'reset'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The motion command: 'walk_forward', 'walk_backward', 'turn_left', 'turn_right', 'stop', 'reset'."
                    },
                    "speed": {
                        "type": "number",
                        "description": "Forward speed (default 0.25)."
                    },
                    "turn": {
                        "type": "number",
                        "description": "Turn rate (default 0.0)."
                    },
                    "duration_sec": {
                        "type": "number",
                        "description": "Duration in seconds (default 1.0)."
                    }
                },
                "required": ["command"]
            }
        },
        handler=move_robot_handler,
        is_async=True,
        description="Sends a high-level motion command: 'walk_forward', 'walk_backward', 'turn_left', 'turn_right', 'stop', 'reset'."
    )

    # 4. get_vision_detections
    async def get_vision_detections_handler(args, **kwargs) -> str:
        try:
            detections = await client.get_vision_detections()
            import json
            return json.dumps(detections, indent=2)
        except Exception as e:
            return f"Error: {e}"

    ctx.register_tool(
        name="get_vision_detections",
        toolset="duck-robot",
        schema={
            "name": "get_vision_detections",
            "description": "Retrieves the latest structured 2D bounding box detections from the active camera (YOLO).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        handler=get_vision_detections_handler,
        is_async=True,
        description="Retrieves the latest structured 2D bounding box detections from the active camera (YOLO)."
    )

    # 5. follow_target
    async def follow_target_handler(args, **kwargs) -> str:
        target_label = args.get("target_label", "chair")
        follow_height = args.get("follow_height", 380.0)
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

    ctx.register_tool(
        name="follow_target",
        toolset="duck-robot",
        schema={
            "name": "follow_target",
            "description": "Commands the robot to actively search for and walk toward a visual target (e.g. 'chair').",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_label": {
                        "type": "string",
                        "description": "Target label (e.g. 'chair')."
                    },
                    "follow_height": {
                        "type": "number",
                        "description": "Height tracking target (default 380.0)."
                    }
                },
                "required": []
            }
        },
        handler=follow_target_handler,
        is_async=True,
        description="Commands the robot to actively search for and walk toward a visual target (e.g. 'chair')."
    )

    # 6. stop_following
    async def stop_following_handler(args, **kwargs) -> str:
        try:
            res = await client.stop_following()
            import json
            return json.dumps(res, indent=2)
        except Exception as e:
            return f"Error: {e}"

    ctx.register_tool(
        name="stop_following",
        toolset="duck-robot",
        schema={
            "name": "stop_following",
            "description": "Stops the active visual target follower and halts the robot.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        handler=stop_following_handler,
        is_async=True,
        description="Stops the active visual target follower and halts the robot."
    )

    # 7. capture_vision_frame
    async def capture_vision_frame_handler(args, **kwargs) -> str:
        try:
            frame_bytes = await client.get_vision_frame()
            import time
            from pathlib import Path
            
            cache_dir = Path.home() / ".hermes" / "cache" / "duck_robot"
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = int(time.time())
            file_path = cache_dir / f"frame_{timestamp}.jpg"
            
            with open(file_path, "wb") as f:
                f.write(frame_bytes)
            
            return f"Frame captured successfully: {file_path}"
        except Exception as e:
            return f"Error capturing frame: {e}"

    ctx.register_tool(
        name="capture_vision_frame",
        toolset="duck-robot",
        schema={
            "name": "capture_vision_frame",
            "description": "Captures the latest RGB frame from the robot's FPV camera and saves it as a local JPEG file. Returns the path.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        handler=capture_vision_frame_handler,
        is_async=True,
        description="Captures the latest RGB frame from the robot's FPV camera and saves it as a local JPEG file. Returns the path."
    )

    # 8. robot_speak
    async def robot_speak_handler(args, **kwargs) -> str:
        message = args.get("message")
        try:
            try:
                from hermes_tools import text_to_speech
                audio_path = text_to_speech(text=message)
                # Play it out loud using afplay on macOS
                import subprocess
                subprocess.Popen(["afplay", audio_path])
                return f"Robot said: '{message}'. Audio saved at: {audio_path}"
            except ImportError:
                import subprocess
                from pathlib import Path
                import time
                
                cache_dir = Path.home() / ".hermes" / "cache" / "duck_robot"
                cache_dir.mkdir(parents=True, exist_ok=True)
                timestamp = int(time.time())
                audio_path = cache_dir / f"speech_{timestamp}.aiff"
                
                # Render to file so we can return a valid path
                subprocess.run(["say", "-v", "Tünde", "-o", str(audio_path), message])
                
                # Play the generated audio file out loud in the background
                subprocess.Popen(["afplay", str(audio_path)])
                
                return f"Robot said: '{message}'. Audio saved at: {audio_path} and played out loud."
        except Exception as e:
            # Generic background say fallback
            try:
                import subprocess
                subprocess.Popen(["say", "-v", "Tünde", message])
                return f"Robot said (direct say): '{message}'"
            except Exception as inner_e:
                return f"Error speaking: {e} (inner: {inner_e})"

    ctx.register_tool(
        name="robot_speak",
        toolset="duck-robot",
        schema={
            "name": "robot_speak",
            "description": "Makes the robot speak a message using text-to-speech. Returns the audio path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to speak."
                    }
                },
                "required": ["message"]
            }
        },
        handler=robot_speak_handler,
        is_async=True,
        description="Makes the robot speak a message using text-to-speech. Returns the audio path."
    )

    # 9. listen_to_audio
    async def listen_to_audio_handler(args, **kwargs) -> str:
        audio_path = args.get("audio_path", "")
        duration_sec = args.get("duration_sec", 5.0)
        try:
            import speech_recognition as sr
            from pathlib import Path
            
            recognizer = sr.Recognizer()
            
            if audio_path and Path(audio_path).exists():
                with sr.AudioFile(audio_path) as source:
                    audio = recognizer.record(source)
                text = recognizer.recognize_google(audio)
                return f"Heard (from file): {text}"
            else:
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source)
                    return f"Listening for {duration_sec} seconds..."
        except ImportError:
            return "Speech recognition not available (install speech_recognition)"
        except Exception as e:
            return f"Error listening: {e}"

    ctx.register_tool(
        name="listen_to_audio",
        toolset="duck-robot",
        schema={
            "name": "listen_to_audio",
            "description": "Transcribes an audio file to text using speech recognition.",
            "parameters": {
                "type": "object",
                "properties": {
                    "audio_path": {
                        "type": "string",
                        "description": "Optional path to a local audio file."
                    },
                    "duration_sec": {
                        "type": "number",
                        "description": "Listening duration in seconds if no audio path is provided."
                    }
                },
                "required": []
            }
        },
        handler=listen_to_audio_handler,
        is_async=True,
        description="Transcribes an audio file to text using speech recognition."
    )