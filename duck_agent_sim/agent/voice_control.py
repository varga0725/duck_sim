import asyncio
import os
import re
import sys
import argparse
from typing import Dict, Any, Optional

try:
    import speech_recognition as sr
    import whisper
except ImportError:
    import warnings
    warnings.warn(
        "Voice control dependencies (SpeechRecognition, openai-whisper) are missing.\n"
        "To run local voice control, please install:\n"
        "  pip install SpeechRecognition openai-whisper sounddevice numpy\n"
        "Also ensure 'ffmpeg' and 'portaudio' are installed on your system (e.g. 'brew install portaudio ffmpeg' or 'apt-get install portaudio19-dev ffmpeg')."
    )
    # Define fallback mock classes so that the module can still be imported and tested
    class MockSR:
        class Recognizer:
            def __init__(self):
                self.dynamic_energy_threshold = True
                self.pause_threshold = 0.8
            def adjust_for_ambient_noise(self, source, duration=1.0):
                pass
            def listen(self, source, timeout=10, phrase_time_limit=5):
                return "mock_audio"
            def recognize_whisper(self, audio, model="tiny", language="hungarian"):
                return "előre"
            def recognize_google(self, audio, language="hu-HU"):
                return "előre"
        class Microphone:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
            @staticmethod
            def list_microphone_names():
                return []
        class WaitTimeoutError(Exception):
            pass
    sr = MockSR()
    
    class MockWhisper:
        def load_model(self, size):
            class DummyModel:
                def transcribe(self, audio):
                    return {"text": "előre"}
            return DummyModel()
    whisper = MockWhisper()


from duck_agent_sim.agent.duck_agent import DuckAgent
from duck_agent_sim.agent.hermes_delegator import HermesMode
from duck_agent_sim.schemas import FollowerConfigSchema
from duck_agent_sim.agent.gemini_live_client import GeminiLiveController

# Hungarian command patterns mapped to their respective robot actions
# Includes robust support for common accents, spelling variations, and typos (e.g., o instead of ő)
COMMAND_MAP = {
    "walk_forward": re.compile(r"\b(el[őo]re|el[őo]rehalad|menj[ ]*el[őo]re|s[ée]t[áa]lj[ ]*el[őo]re|el[őo]r|haladj[ ]*el[őo]re|l[őo]re)\b", re.IGNORECASE),
    "walk_backward": re.compile(r"\b(h[áa]tra|menj[ ]*h[áa]tra|s[ée]t[áa]lj[ ]*h[áa]tra|h[áa]tr)\b", re.IGNORECASE),
    "turn_left": re.compile(r"\b(balra|bal|balla|ford[uü]lj[ ]*balra|menj[ ]*balra)\b", re.IGNORECASE),
    "turn_right": re.compile(r"\b(jobbra|jobb|jobra|ford[uü]lj[ ]*jobbra|menj[ ]*jobbra)\b", re.IGNORECASE),
    "stop": re.compile(r"\b([áa]llj|allj|alj|[áa]llj[ ]*meg|meg[áa]llj|stop|v[ée]ge|sz[üu]net)\b", re.IGNORECASE),
    "reset": re.compile(r"\b([úu]jra|alaphelyzet|alap|vissza[áa]ll[íi]t|reset)\b", re.IGNORECASE),
    "stop_following": re.compile(r"\b(ne[ ]*k[öo]vesd|ne[ ]*sz[ée]k|[áa]ll[íi]tsd[ ]*le[ ]*a[ ]*k[öo]vet[ée]st|k[öo]vet[ée]s[ ]*le[áa]ll[íi]t[áa]sa)\b", re.IGNORECASE),
    "follow_chair": re.compile(r"\b(k[öo]vesd[ ]*a[ ]*sz[ée]ket|k[öo]vesd[ ]*sz[ée]ket|keresd[ ]*sz[ée]ket|k[öo]vesd|sz[ée]k|sz[ée]ket)\b", re.IGNORECASE),
}


class LocalVoiceController:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        model_size: str = "base",
        engine: str = "google",
        hermes_mode: HermesMode = "oneshot",
        device: Optional[str] = None,
        live: bool = False,
    ):
        """
        Initializes the Voice Controller.
        - base_url: The simulator bridge URL.
        - model_size: Whisper model size ('tiny', 'base', 'small'). 'base' is recommended for excellent Hungarian.
        - engine: Transcription engine: 'google' (online, high accuracy) or 'whisper' (local/offline).
        - hermes_mode: How to reach Hermes for complex tasks: 'oneshot', 'warm_cli', or 'http'.
        - device: Device name substring (e.g. 'iPhone') or integer index.
        """
        self.agent = DuckAgent(bridge_url=base_url, hermes_mode=hermes_mode)
        self.model_size = model_size
        self.engine = engine.lower().strip()
        self.hermes_mode = hermes_mode
        self.recognizer = sr.Recognizer()
        
        # Resolve microphone device index
        self.device_index = None
        if device is not None:
            self.device_index = self.resolve_device(device)
        
        # Adjust recognizer properties for better responsiveness
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8  # Wait 0.8s of silence before phrasing completes

        self.whisper_model = None
        self.calibrated = False
        self.live = live

    def resolve_device(self, device_input: str) -> Optional[int]:
        """Resolves a device name or index string to a PyAudio device index."""
        try:
            # Check if it's an integer index directly
            return int(device_input)
        except ValueError:
            pass
        
        # It's a string, scan available names
        try:
            names = sr.Microphone.list_microphone_names()
            print(f"[*] Scanning microphone devices for '{device_input}'...")
            for idx, name in enumerate(names):
                if device_input.lower() in name.lower():
                    print(f"[+] Matched microphone '{name}' to index {idx}.")
                    return idx
            print(f"[!] Warning: No microphone found matching '{device_input}'. Available: {names}")
        except Exception as e:
            print(f"[!] Error scanning microphone devices: {e}")
        return None

    def load_model(self):
        """Pre-loads the Whisper model locally to avoid latency on first command."""
        if self.whisper_model is not None:
            return
        print(f"[*] Loading Whisper model '{self.model_size}' locally (Hungarian language configuration)...")
        # Under the hood, sr.recognize_whisper uses whisper.load_model
        self.whisper_model = whisper.load_model(self.model_size)
        print("[+] Local Whisper model loaded and ready.")

    def speak(self, text: str):
        """Speaks a message out loud using the macOS 'say' command with Hungarian voice 'Tünde'."""
        if not text:
            return
        # Clean markdown, tags, thought bubbles, and code blocks for speech
        cleaned = re.sub(r'[*_`#\-]', ' ', text)
        cleaned = re.sub(r'\[.*?\]', '', cleaned)
        cleaned = re.sub(r'<.*?>', '', cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            return
        
        print(f"[🔊] Speaking: '{cleaned[:60]}...'")
        try:
            import subprocess
            # Speak synchronously so we don't capture our own voice
            subprocess.run(["say", "-v", "Tünde", cleaned])
            import time
            time.sleep(0.5)  # Let the room echo settle before listening again
        except Exception as e:
            print(f"[!] Error speaking: {e}", file=sys.stderr)

    # NOTE: execute_action() and parse_command() are no longer needed.
    # The DuckAgent.process() method handles routing and execution internally.

    def listen_and_process_sync(self) -> Optional[str]:
        """Synchronously captures microphone audio and transcribes it."""
        with sr.Microphone(device_index=self.device_index) as source:
            if not self.calibrated:
                print("\n[🎧] Calibrating microphone for ambient noise (1 second)...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
                self.calibrated = True
                print("[+] Microphone calibrated and ready!")
            
            print("[+] Microphone ready! Speak now (in Hungarian)...")
            
            try:
                # Capture audio stream
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=5)
                
                if self.engine == "google":
                    print("[*] Audio captured, transcribing online using Google Speech Recognition...")
                    try:
                        transcription = self.recognizer.recognize_google(
                            audio,
                            language="hu-HU"
                        )
                        return transcription
                    except Exception as e:
                        print(f"[!] Google Speech Recognition error: {e}")
                        print("[*] Falling back to local Whisper offline transcription...")
                
                print("[*] Audio captured, transcribing offline using local Whisper...")
                if self.whisper_model is None:
                    self.load_model()
                
                # Transcribe using local Whisper model
                transcription = self.recognizer.recognize_whisper(
                    audio,
                    model=self.model_size,
                    language="hungarian"
                )
                return transcription
            except sr.WaitTimeoutError:
                print("[-] Listening timed out (no speech detected).")
                return None
            except Exception as e:
                print(f"[!] Transcription error: {e}", file=sys.stderr)
                return None

    # NOTE: send_to_hermes() is no longer needed.
    # The DuckAgent.process() → HermesDelegator handles Hermes communication.

    async def start_voice_loop(self):
        """Asynchronous main loop for listening and commanding the robot via DuckAgent or Gemini Live."""
        if getattr(self, "live", False):
            live_controller = GeminiLiveController(
                bridge_url=self.agent._bridge_url,
                hermes_mode=self.hermes_mode,
                device=self.device_index,
            )
            await live_controller.start()

            print("\n=======================================================")
            print("   🦆 DUCK ROBOT GEMINI LIVE MULTIMODAL CONTROLLER 🦆  ")
            print("   ═══════ Bidirectional Voice & FPV Vision ═══════     ")
            print("=======================================================")
            print(f"Target Bridge:  {live_controller.bridge_url}")
            print(f"Voice Mode:     REAL-TIME STREAMING (wss)")
            print(f"Vision Stream:  FPV CAMERA @ 2 FPS")
            print(f"Routing:        DIRECT (<100ms) / HERMES DELEGATION")
            print("Press Ctrl+C to terminate.")
            print("=======================================================")

            try:
                await live_controller.run()
            finally:
                await live_controller.stop()
            return

        # Pre-load Whisper model ONLY if whisper engine is chosen
        if self.engine == "whisper":
            self.load_model()

        # Pre-warm the DuckAgent (starts Hermes warm pool if configured)
        await self.agent.start()

        print("\n=======================================================")
        print("   🦆 DUCK ROBOT LOCAL HUNGARIAN VOICE CONTROL NODE 🦆  ")
        print("   ═══════ Powered by DuckAgent Smart Router ═══════    ")
        print("=======================================================")
        print(f"Target Bridge:  {self.agent._bridge_url}")
        print(f"Speech Engine:  {self.engine.upper()}")
        print(f"Hermes Mode:    {self.hermes_mode.upper()}")
        print(f"Routing:        SMART (direct <100ms / hermes delegation)")
        if self.engine == "whisper" or self.whisper_model is not None:
            print(f"Whisper Model:  {self.model_size}")
        print("Language:       Hungarian (Magyar)")
        print("Press Ctrl+C to terminate.")
        print("=======================================================")

        try:
            while True:
                # Run blocking mic input & transcription in an executor
                loop = asyncio.get_running_loop()
                transcription = await loop.run_in_executor(
                    None, self.listen_and_process_sync
                )

                if transcription:
                    # Route everything through DuckAgent — it decides
                    # whether to handle locally or delegate to Hermes
                    intent, response = await self.agent.process_with_intent(
                        transcription
                    )

                    # Pretty-print the result
                    source_icon = "⚡" if response.source == "direct" else "🤖"
                    print(f"\n{'=' * 55}")
                    print(
                        f"{source_icon}  [{response.source.upper()}]  "
                        f"action={response.action}  "
                        f"latency={response.latency_ms:.0f}ms"
                    )
                    print(f"{'=' * 55}")

                    if response.hermes_raw:
                        print(response.hermes_raw)

                    if not response.success:
                        print(f"[!] Error: {response.error}")

                    print(f"{'=' * 55}\n")

                    # Speak the response out loud
                    if response.speech:
                        self.speak(response.speech)

                # Short sleep before next listening phase
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[Voice Control] KeyboardInterrupt caught, exiting...")
            import sys
            sys.exit(0)
        finally:
            await self.agent.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Duck Robot Local Hungarian Voice Control Node (DuckAgent Smart Router)"
    )
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8765", help="Bridge Server URL")
    parser.add_argument("--model", type=str, default="base", help="Whisper model: tiny, base, small")
    parser.add_argument(
        "--engine", type=str, default="google",
        choices=["google", "whisper"],
        help="Transcription engine: google (default, online), whisper (offline)",
    )
    parser.add_argument("--device", type=str, default=None, help="Microphone device name substring (e.g. 'iPhone') or integer index")
    parser.add_argument(
        "--hermes-mode", type=str, default="oneshot",
        choices=["oneshot", "warm_cli", "http"],
        help="How to reach Hermes for complex tasks (default: oneshot)",
    )
    parser.add_argument("--live", action="store_true", help="Run with bidirectional real-time Gemini Live WebSocket API")
    args = parser.parse_args()

    controller = LocalVoiceController(
        base_url=args.url,
        model_size=args.model,
        engine=args.engine,
        hermes_mode=args.hermes_mode,
        device=args.device,
        live=args.live,
    )

    try:
        asyncio.run(controller.start_voice_loop())
    except KeyboardInterrupt:
        print("\n[!] Voice control terminated by user.")
        sys.exit(0)
