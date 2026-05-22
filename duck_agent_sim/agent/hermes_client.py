import asyncio
import json
import logging
from typing import Callable, List, Dict, Any, Optional
import httpx
import websockets

from duck_agent_sim.schemas import (
    RobotCommand,
    RobotState,
    CommandResponse,
    SensorsState,
    FollowerConfigSchema,
    SafetyConfig,
    CommandType,
)

logger = logging.getLogger("hermes-client")


class HermesRobotClient:
    """
    An asynchronous, premium Python SDK for the Duck Simulator API.
    Designed for tight integration with high-level LLM agents (such as Hermes or OpenClaw).
    
    Provides:
      - Asynchronous REST methods for all movement, safety, and vision API endpoints.
      - A background WebSocket telemetry listener for real-time state feedback (10Hz).
      - Event-driven callbacks for telemetry, stability alerts, and status changes.
      - Auto-recovery/safety hooks that integrate natively with the simulator's preflight bounds.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8765"):
        self.base_url = base_url.rstrip("/")
        self.ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        self.http_client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)
        self._telemetry_task: Optional[asyncio.Task] = None
        self._ws_connection = None
        self._running = False

        # Event callbacks
        self._telemetry_callbacks: List[Callable[[RobotState], None]] = []
        self._fall_callbacks: List[Callable[[RobotState], None]] = []
        self._status_change_callbacks: List[Callable[[str, str], None]] = []
        self._last_state: Optional[RobotState] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Cleanly closes the http client and any active background telemetry task."""
        self._running = False
        await self.stop_telemetry_stream()
        await self.http_client.aclose()
        logger.info("Hermes Robot Client closed successfully.")

    # ----------------------------------------------------
    # Event Registration Interfaces
    # ----------------------------------------------------
    def on_telemetry(self, callback: Callable[[RobotState], None]):
        """Registers a callback triggered on every 10Hz WebSocket telemetry state update."""
        self._telemetry_callbacks.append(callback)
        return callback

    def on_fall(self, callback: Callable[[RobotState], None]):
        """Registers a callback triggered whenever the robot stability monitor detects a fall/instability."""
        self._fall_callbacks.append(callback)
        return callback

    def on_status_change(self, callback: Callable[[str, str], None]):
        """Registers a callback triggered when the robot status changes (e.g. from 'idle' to 'walking')."""
        self._status_change_callbacks.append(callback)
        return callback

    # ----------------------------------------------------
    # REST Command / Control Endpoints
    # ----------------------------------------------------
    async def get_state(self) -> RobotState:
        """Fetches the current high-level RobotState from the REST API."""
        r = await self.http_client.get("/state")
        r.raise_for_status()
        state = RobotState(**r.json())
        self._update_internal_state(state)
        return state

    async def get_sensors_state(self) -> SensorsState:
        """Fetches raw simulator sensor channels (IMU + Feet contact velocities/orientations)."""
        r = await self.http_client.get("/sensors/state")
        r.raise_for_status()
        return SensorsState(**r.json())

    async def send_command(
        self,
        command: CommandType,
        speed: float = 0.25,
        turn: float = 0.0,
        duration_sec: float = 1.0,
        safety_config: Optional[SafetyConfig] = None,
    ) -> CommandResponse:
        """
        Sends a high-level motion command with safety enforcement limits.
        If a fall/instability is detected, the simulator automatically initiates stop+reset recovery.
        """
        if safety_config is None:
            safety_config = SafetyConfig()

        cmd = RobotCommand(
            command=command,
            speed=speed,
            turn=turn,
            duration_sec=duration_sec,
            safety=safety_config,
        )

        r = await self.http_client.post("/command", json=cmd.model_dump())
        r.raise_for_status()
        response = CommandResponse(**r.json())
        self._update_internal_state(response.state)
        return response

    async def stop(self) -> RobotState:
        """Immediately halts robot motion and resets gait cycle."""
        r = await self.http_client.post("/stop")
        r.raise_for_status()
        state = RobotState(**r.json()["state"])
        self._update_internal_state(state)
        return state

    async def reset(self) -> RobotState:
        """Resets the robot coordinates to the origin, clears fallen status, and re-stabilizes body."""
        r = await self.http_client.post("/reset")
        r.raise_for_status()
        state = RobotState(**r.json()["state"])
        self._update_internal_state(state)
        return state

    async def execute_walk_square_scenario(self) -> Dict[str, Any]:
        """Executes a pre-scripted square waddle path with step-by-step safety evaluations."""
        r = await self.http_client.post("/scenario/walk-square")
        r.raise_for_status()
        return r.json()

    # ----------------------------------------------------
    # Vision & Follower API Endpoints
    # ----------------------------------------------------
    async def get_vision_frame(self) -> bytes:
        """Retrieves the latest camera frame as raw JPEG bytes (ideal for feeding into VLM visual inputs)."""
        r = await self.http_client.get("/vision/frame")
        r.raise_for_status()
        return r.content

    async def get_vision_detections(self) -> List[Dict[str, Any]]:
        """Retrieves structured bounding box object detections from the active camera (YOLO)."""
        r = await self.http_client.get("/vision/detections")
        r.raise_for_status()
        return r.json().get("objects", [])

    async def get_vision_state(self) -> Dict[str, Any]:
        """Gets the status, queue length, and FPS statistics of the vision perception loop."""
        r = await self.http_client.get("/vision/state")
        r.raise_for_status()
        return r.json()

    async def start_following(self, config: Optional[FollowerConfigSchema] = None) -> Dict[str, Any]:
        """
        Starts the active vision target follower (commands the robot to face and walk toward target).
        Optionally configures follow PID gains, target bounding heights, or deadman timeouts.
        """
        payload = config.model_dump() if config else {}
        r = await self.http_client.post("/vision/follow/start", json=payload)
        r.raise_for_status()
        return r.json()

    async def stop_following(self) -> Dict[str, Any]:
        """Stops the active vision follower and commands the robot base to halt."""
        r = await self.http_client.post("/vision/follow/stop")
        r.raise_for_status()
        return r.json()

    async def get_follow_status(self) -> Dict[str, Any]:
        """Gets telemetry and control states (state, target tracking errors, PID outputs) of target follower."""
        r = await self.http_client.get("/vision/follow/status")
        r.raise_for_status()
        return r.json()

    async def get_map(self) -> Dict[str, Any]:
        """Retrieves the 2D occupancy grid matrix and semantic landmarks from the simulator."""
        r = await self.http_client.get("/map")
        r.raise_for_status()
        return r.json()

    async def reset_map(self) -> Dict[str, Any]:
        """Resets the 2D occupancy grid and landmark memory."""
        r = await self.http_client.post("/map/reset")
        r.raise_for_status()
        return r.json()

    # ----------------------------------------------------
    # WebSocket Real-Time Telemetry Stream
    # ----------------------------------------------------
    async def start_telemetry_stream(self):
        """Starts the background task to stream real-time telemetry from the simulator WebSocket (10Hz)."""
        if self._telemetry_task is not None:
            return

        self._running = True
        self._telemetry_task = asyncio.create_task(self._listen_to_telemetry())
        logger.info(f"Subscribed to real-time telemetry at: {self.ws_url}")

    async def stop_telemetry_stream(self):
        """Stops the background task and closes the active WebSocket connection."""
        self._running = False
        if self._ws_connection:
            try:
                await self._ws_connection.close()
            except Exception:
                pass
            self._ws_connection = None

        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
            self._telemetry_task = None
        logger.info("Unsubscribed from real-time telemetry feed.")

    async def _listen_to_telemetry(self):
        """WebSocket consumer loop connecting to the simulator telemetry."""
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self._ws_connection = ws
                    logger.info("WebSocket telemetry stream connected.")
                    while self._running:
                        message = await ws.recv()
                        try:
                            data = json.loads(message)
                            state = RobotState(**data)
                            self._update_internal_state(state)
                            
                            # Trigger telemetry callbacks
                            for cb in self._telemetry_callbacks:
                                try:
                                    cb(state)
                                except Exception as e:
                                    logger.error(f"Error in telemetry callback: {e}")
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to decode telemetry JSON message: {message}")
                        except Exception as e:
                            logger.error(f"Error parsing state: {e}")
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as e:
                if self._running:
                    logger.warning(f"Telemetry WebSocket disconnected/refused ({e}). Reconnecting in 2 seconds...")
                    await asyncio.sleep(2.0)
            except Exception as e:
                if self._running:
                    logger.error(f"Unexpected telemetry WebSocket loop error: {e}. Retrying in 2 seconds...")
                    await asyncio.sleep(2.0)

    def _update_internal_state(self, new_state: RobotState):
        """Processes state change events and updates internal cache."""
        old_state = self._last_state
        self._last_state = new_state

        if old_state is None:
            return

        # Trigger fall detection callbacks
        if new_state.fallen and not old_state.fallen:
            logger.warning("STABILITY WARNING: Robot fell or breached pitch/roll constraints!")
            for cb in self._fall_callbacks:
                try:
                    cb(new_state)
                except Exception as e:
                    logger.error(f"Error in fall callback: {e}")

        # Trigger status change callbacks
        if new_state.status != old_state.status:
            for cb in self._status_change_callbacks:
                try:
                    cb(old_state.status, new_state.status)
                except Exception as e:
                    logger.error(f"Error in status change callback: {e}")
