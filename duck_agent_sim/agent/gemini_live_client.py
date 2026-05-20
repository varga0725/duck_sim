"""
GeminiLiveController — Premium bidirectional WebSockets client for the Gemini Multimodal Live API.

Handles real-time streaming of:
- Microphone audio (16kHz PCM mono 16-bit little-endian) -> Gemini Live
- FPV camera frames (JPEG @ 2 FPS) -> Gemini Live
- Speakers audio (24kHz PCM mono 16-bit little-endian) <- Gemini Live
- Bidirectional Tool Calls (move_robot, follow_target, route_to_hermes)
"""

import asyncio
import base64
import json
import logging
import os
import queue
import re
import threading
import traceback
from typing import Optional
import numpy as np
import websockets
import httpx

try:
    import sounddevice as sd
except ImportError:
    sd = None

from duck_agent_sim.agent.direct_controller import DirectController
from duck_agent_sim.agent.hermes_delegator import HermesDelegator, HermesMode
from duck_agent_sim.agent.smart_router import Intent

logger = logging.getLogger("gemini-live-client")


class GeminiLiveController:
    """
    Manages a continuous real-time WebSocket session with the Google Gemini Multimodal Live API.
    Stream mic audio + camera frames, play back spoken AI responses, and execute tool calls.
    """

    def __init__(
        self,
        bridge_url: str = "http://127.0.0.1:8765",
        model: str = "models/gemini-2.5-flash-native-audio-latest",
        voice_name: str = "Puck",
        hermes_mode: HermesMode = "oneshot",
        device: Optional[str] = None,
    ):
        self.bridge_url = bridge_url
        self.model = model
        self.voice_name = voice_name
        self.hermes_mode = hermes_mode
        self.device_name_or_index = device

        self.direct = DirectController(bridge_url=self.bridge_url)
        self.hermes = HermesDelegator(mode=self.hermes_mode)

        self.api_key = self._resolve_api_key()
        self.ws_uri = (
            f"wss://generativelanguage.googleapis.com/ws/"
            f"google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
            f"?key={self.api_key}"
        )

        self.audio_input_queue = asyncio.Queue()
        self.audio_output_queue = queue.Queue()
        self._playback_thread = None
        self._playback_running = False
        self._running = False
        self._ws = None
        self._tasks = []
        self._mic_stream = None
        self._speaker_stream = None
        self._device_index = None

        self.is_speaking = False
        self._last_speaker_time = 0.0

    def _resolve_api_key(self) -> str:
        """Resolves Google / Gemini API key from env or global ~/.hermes/.env file."""
        # 1. Check environment variables
        for key in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
            val = os.getenv(key)
            if val:
                logger.info(f"Using {key} from environment variables.")
                return val

        # 2. Check ~/.hermes/.env file
        env_path = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k in ["GEMINI_API_KEY", "GOOGLE_API_KEY"] and v:
                                logger.info(f"Loaded {k} from {env_path}")
                                return v
            except Exception as e:
                logger.warning(f"Failed to read {env_path}: {e}")

        raise ValueError(
            "Could not resolve GEMINI_API_KEY or GOOGLE_API_KEY. "
            "Please export it or set it in ~/.hermes/.env"
        )

    def _resolve_mic_device(self) -> Optional[int]:
        """Resolves microphone device index if a filter string was specified."""
        if not sd or self.device_name_or_index is None:
            return None

        try:
            # Check if direct integer index
            return int(self.device_name_or_index)
        except ValueError:
            pass

        try:
            devices = sd.query_devices()
            logger.info(f"Scanning audio devices for '{self.device_name_or_index}'...")
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "")
                    if self.device_name_or_index.lower() in name.lower():
                        logger.info(f"Matched microphone '{name}' to index {idx}.")
                        return idx
            logger.warning(f"No input device matched '{self.device_name_or_index}'. Available: {devices}")
        except Exception as e:
            logger.error(f"Error scanning audio devices: {e}")
        return None

    async def start(self):
        """Starts the background systems (Hermes Warm CLI pool, etc.)."""
        self._device_index = self._resolve_mic_device()
        await self.hermes.start()
        logger.info("GeminiLiveController background subsystems started.")

    async def stop(self):
        """Gracefully halts the WebSocket connection and local streams."""
        self._running = False
        self._playback_running = False
        
        if self._playback_thread:
            try:
                self.audio_output_queue.put_nowait(None)
            except Exception:
                pass
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._playback_thread.join, 1.0)
            self._playback_thread = None

        # Cancel tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        # Close streams
        if self._mic_stream:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception:
                pass
            self._mic_stream = None

        if self._speaker_stream:
            try:
                self._speaker_stream.stop()
                self._speaker_stream.close()
            except Exception:
                pass
            self._speaker_stream = None

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        await self.direct.close()
        await self.hermes.stop()
        logger.info("GeminiLiveController stopped.")

    def _play_audio_loop(self):
        """Dedicated background thread to play PCM chunks sequentially in strict FIFO order."""
        import time
        logger.info("Speaker playback thread started.")
        while self._playback_running:
            try:
                # Block with timeout to check self._playback_running
                chunk = self.audio_output_queue.get(timeout=0.1)
            except queue.Empty:
                self.is_speaking = False
                continue
            if chunk is None:
                self.is_speaking = False
                break
            
            self.is_speaking = True
            self._last_speaker_time = time.time()
            try:
                if self._speaker_stream:
                    self._speaker_stream.write(chunk)
                    self._last_speaker_time = time.time()
            except Exception as e:
                logger.error(f"Error in speaker playback thread: {e}")
            finally:
                self.audio_output_queue.task_done()
        self.is_speaking = False
        logger.info("Speaker playback thread stopped.")

    async def run(self):
        """Connects to the WebSocket endpoint and starts all async workers."""
        self._running = True
        logger.info(f"Connecting to Gemini Live API: {self.ws_uri.split('?')[0]}")

        async with websockets.connect(self.ws_uri) as ws:
            self._ws = ws
            logger.info("WebSocket connection established successfully!")

            # 1. Send Setup payload
            setup_payload = self._build_setup_payload()
            await ws.send(json.dumps(setup_payload))
            logger.info("Session Setup payload transmitted successfully.")

            # 2. Spawn concurrent stream workers
            self._tasks = [
                asyncio.create_task(self._mic_input_loop()),
                asyncio.create_task(self._camera_vision_loop()),
                asyncio.create_task(self._receive_loop()),
            ]

            # Wait for execution or termination
            await asyncio.gather(*self._tasks)

    def _build_setup_payload(self) -> dict:
        """Constructs the initial setup configuration message."""
        return {
            "setup": {
                "model": self.model,
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": self.voice_name
                            }
                        }
                    }
                },
                "systemInstruction": {
                    "parts": [
                        {
                            "text": (
                                "Te a Duck Robot barátságos, beszélő, látó és cselekvő AI asszisztense vagy. "
                                "Mindig magyarul beszélj a felhasználóval! A robot FPV kameráját látod, amit "
                                "JPEG képkockákként kapsz meg folyamatosan. Bármikor, ha a felhasználó olyat kér, "
                                "ami mozgással kapcsolatos vagy követéssel kapcsolatos, használd a megfelelő eszközhívást (tool call). "
                                "Ha a felhasználó egy szoftverfejlesztési feladatot kér tőled (pl. kód javítása, fájl megnyitása, git), "
                                "akkor a 'route_to_hermes' eszközt hívd meg a teljes utasítással."
                            )
                        }
                    ]
                },
                "tools": [
                    {
                        "functionDeclarations": [
                            {
                                "name": "move_robot",
                                "description": "Sends a direct motion command to the robot.",
                                "parameters": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "command": {
                                            "type": "STRING",
                                            "enum": ["walk_forward", "walk_backward", "turn_left", "turn_right", "stop", "reset"],
                                            "description": "The exact motion command to execute."
                                        },
                                        "speed": {"type": "NUMBER", "description": "Linear speed factor (0.0 to 1.0)"},
                                        "turn": {"type": "NUMBER", "description": "Yaw rate factor (-1.0 to 1.0)"},
                                        "duration_sec": {"type": "NUMBER", "description": "Motion duration in seconds"}
                                    },
                                    "required": ["command"]
                                }
                            },
                            {
                                "name": "follow_target",
                                "description": "Commands the robot to actively track and follow a visual target.",
                                "parameters": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "target_label": {"type": "STRING", "description": "The label of the object to track, e.g. 'chair'"}
                                    },
                                    "required": ["target_label"]
                                }
                            },
                            {
                                "name": "route_to_hermes",
                                "description": "Routes a complex workspace, filesystem, coding, or git task to the background Hermes Developer Agent.",
                                "parameters": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "task": {"type": "STRING", "description": "The description of the software task to perform."}
                                    },
                                    "required": ["task"]
                                }
                            }
                        ]
                    }
                ]
            }
        }

    # ──────────────────────────────────────────────────────
    # Input Loop: Microphone
    # ──────────────────────────────────────────────────────
    async def _mic_input_loop(self):
        """Continuously captures audio from local microphone and streams it to Gemini Live."""
        if not sd:
            logger.warning("sounddevice is missing. Microphone input disabled.")
            return

        def callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Mic status: {status}")
            
            import time
            is_currently_speaking = self.is_speaking or (time.time() - self._last_speaker_time < 0.5)
            if is_currently_speaking:
                # Immediate microphone gate in callback to prevent acoustic echo feedback latency gaps
                self.audio_input_queue.put_nowait(bytes(len(indata)))
            else:
                self.audio_input_queue.put_nowait(bytes(indata))

        try:
            logger.info("Initializing local microphone input stream (16kHz mono PCM16)...")
            self._mic_stream = sd.RawInputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                callback=callback,
                device=self._device_index,
            )
            with self._mic_stream:
                while self._running:
                    data = await self.audio_input_queue.get()
                    if not self._running or not self._ws:
                        break
                    
                    # Prevent acoustic feedback: if speaker is active, send silent audio chunks.
                    # This prevents the server VAD from incorrectly cutting off the robot's own responses.
                    import time
                    is_currently_speaking = self.is_speaking or (time.time() - self._last_speaker_time < 0.5)
                    if is_currently_speaking:
                        data = bytes(len(data))

                    payload = {
                        "realtimeInput": {
                            "mediaChunks": [
                                {
                                    "mimeType": "audio/pcm;rate=16000",
                                    "data": base64.b64encode(data).decode("utf-8"),
                                }
                            ]
                        }
                    }
                    await self._ws.send(json.dumps(payload))
        except Exception as e:
            logger.error(f"Microphone input stream crashed: {e}")

    # ──────────────────────────────────────────────────────
    # Input Loop: Camera Vision (FPV)
    # ──────────────────────────────────────────────────────
    async def _camera_vision_loop(self):
        """Periodically grabs camera frames from MuJoCo Bridge and streams them to Gemini Live at 2 FPS."""
        logger.info("Starting visual FPV camera stream (2 FPS)...")
        while self._running:
            if not self._ws:
                await asyncio.sleep(0.5)
                continue

            try:
                frame_bytes = await self.direct.client.get_vision_frame()
                if frame_bytes:
                    payload = {
                        "realtimeInput": {
                            "mediaChunks": [
                                {
                                    "mimeType": "image/jpeg",
                                    "data": base64.b64encode(frame_bytes).decode("utf-8"),
                                }
                            ]
                        }
                    }
                    await self._ws.send(json.dumps(payload))
            except Exception as e:
                logger.debug(f"Failed to fetch or send FPV frame: {e}")

            await asyncio.sleep(0.5)  # 2 FPS

    # ──────────────────────────────────────────────────────
    # Output Loop: Speaker & Receiver
    # ──────────────────────────────────────────────────────
    async def _receive_loop(self):
        """Listens for server responses, handles audio streaming playback, and executes tools."""
        if sd:
            logger.info("Initializing speaker output stream (24kHz mono PCM16)...")
            self._speaker_stream = sd.RawOutputStream(
                samplerate=24000,
                channels=1,
                dtype="int16",
            )
            self._speaker_stream.start()

            # Start background playback thread
            self._playback_running = True
            self._playback_thread = threading.Thread(target=self._play_audio_loop, daemon=True)
            self._playback_thread.start()

        try:
            async for message in self._ws:
                if not self._running:
                    break

                data = json.loads(message)

                # 1. Parse Conversational audio output and server interruption
                server_content = data.get("serverContent") or data.get("server_content")
                if server_content:
                    # Check for server-side interruption (user spoke)
                    if server_content.get("interrupted") or server_content.get("interrupted") is True:
                        logger.info("Received server-side interruption signal from Gemini Live. Clearing playback queue.")
                        # Clear all pending audio chunks in queue
                        while not self.audio_output_queue.empty():
                            try:
                                self.audio_output_queue.get_nowait()
                                self.audio_output_queue.task_done()
                            except (queue.Empty, ValueError):
                                break
                        self.is_speaking = False
                        self._last_speaker_time = 0.0

                    model_turn = server_content.get("modelTurn") or server_content.get("model_turn")
                    if model_turn:
                        parts = model_turn.get("parts") or []
                        for part in parts:
                            inline_data = part.get("inlineData") or part.get("inline_data")
                            if inline_data:
                                raw_data = inline_data.get("data")
                                if raw_data and self._speaker_stream:
                                    audio_bytes = base64.b64decode(raw_data)
                                    # Set speaking state IMMEDIATELY upon queueing to lock microphone before playback thread starts
                                    import time
                                    self.is_speaking = True
                                    self._last_speaker_time = time.time()
                                    self.audio_output_queue.put_nowait(audio_bytes)

                # 2. Parse Tool Calls
                tool_call = data.get("toolCall") or data.get("tool_call")
                if tool_call:
                    function_calls = tool_call.get("functionCalls") or tool_call.get("function_calls") or []
                    for call in function_calls:
                        call_id = call.get("id")
                        name = call.get("name")
                        args = call.get("args") or {}
                        
                        logger.info(f"Received tool call from Gemini: {name} (id={call_id}) with args={args}")
                        
                        # Execute in background task so we don't block the receiver stream
                        asyncio.create_task(self._execute_and_respond_tool(call_id, name, args))

        except websockets.exceptions.ConnectionClosed:
            logger.info("Gemini Live WebSocket connection closed.")
        except Exception as e:
            logger.error(f"Error in receiver loop: {e}\n{traceback.format_exc()}")

    async def _execute_and_respond_tool(self, call_id: str, name: str, args: dict):
        """Runs the requested function and returns the tool response block back to Gemini Live."""
        try:
            result = await self._run_tool(name, args)
        except Exception as e:
            logger.error(f"Error running tool {name}: {e}")
            result = {"success": False, "error": str(e)}

        if not self._ws:
            return

        response_payload = {
            "toolResponse": {
                "functionResponses": [
                    {
                        "id": call_id,
                        "name": name,
                        "response": {
                            "output": result
                        }
                    }
                ]
            }
        }
        try:
            await self._ws.send(json.dumps(response_payload))
            logger.info(f"Sent tool response back to Gemini for {name} (id={call_id})")
        except Exception as e:
            logger.error(f"Failed to transmit tool response for {name}: {e}")

    async def _run_tool(self, name: str, args: dict) -> dict:
        """Executes local robot commands or routes to Hermes in the background."""
        if name == "move_robot":
            command = args.get("command")
            speed = args.get("speed", 0.3)
            turn = args.get("turn", 0.0)
            duration_sec = args.get("duration_sec", 1.5)

            # Map to SmartRouter intent format for direct controller
            intent = Intent(
                action=command,
                route="direct",
                confidence=1.0,
                params={"speed": speed, "turn": turn, "duration_sec": duration_sec},
                raw_text=f"move_robot {command}",
            )
            resp = await self.direct.execute(intent)
            return {
                "success": resp.success,
                "error": resp.error,
                "speech": resp.speech,
                "action": resp.action,
            }

        elif name == "follow_target":
            target_label = args.get("target_label", "chair")
            intent = Intent(
                action="follow_target",
                route="direct",
                confidence=1.0,
                params={"target_label": target_label},
                raw_text=f"follow {target_label}",
            )
            resp = await self.direct.execute(intent)
            return {
                "success": resp.success,
                "error": resp.error,
                "speech": resp.speech,
                "action": resp.action,
            }

        elif name == "route_to_hermes":
            task = args.get("task")
            logger.info(f"Delegating complex task to Hermes background agent: '{task}'")
            resp = await self.hermes.delegate(task)
            return {
                "success": resp.success,
                "error": resp.error,
                "output": resp.hermes_raw,
                "speech": resp.speech,
            }

        else:
            raise ValueError(f"Unknown tool declaration: {name}")
