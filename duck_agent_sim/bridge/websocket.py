import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from duck_agent_sim.schemas import RobotCommand, RobotState
from duck_agent_sim.simulator.instance import active_simulator

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint allowing real-time robot telemetry streaming (at 10Hz)
    and optional asynchronous command ingestion.
    """
    await websocket.accept()

    # Background task to stream states continuously to the client
    async def telemetry_streamer():
        try:
            while True:
                state = active_simulator.get_state()
                # Send robot state as JSON
                await websocket.send_text(state.model_dump_json())
                await asyncio.sleep(0.1)  # Stream at 10Hz
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    # Start streaming telemetry in the background
    streamer_task = asyncio.create_task(telemetry_streamer())

    try:
        while True:
            # Keep connection alive and optionally accept incoming commands
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                # Check if it looks like a command
                if "command" in payload:
                    cmd = RobotCommand(**payload)
                    # Apply the command in the active simulator
                    from duck_agent_sim.services import app_context
                    queue_manager = app_context.registry.get("queue_manager")
                    await queue_manager.submit_command(cmd)
                    
                    # Send acknowledgement
                    await websocket.send_text(json.dumps({
                        "event": "command_received",
                        "status": "accepted",
                        "command": cmd.command
                    }))
            except (json.JSONDecodeError, ValidationError) as e:
                await websocket.send_text(json.dumps({
                    "event": "error",
                    "detail": f"Invalid command payload: {str(e)}"
                }))
    except WebSocketDisconnect:
        pass
    finally:
        # Cancel the streamer task on disconnect
        streamer_task.cancel()
        try:
            await streamer_task
        except asyncio.CancelledError:
            pass
