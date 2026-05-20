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
        class Microphone:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
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


from duck_agent_sim.agent.hermes_client import HermesRobotClient
from duck_agent_sim.schemas import FollowerConfigSchema

# Hungarian command patterns mapped to their respective robot actions
COMMAND_MAP = {
    "walk_forward": re.compile(r"\b(előre|sétálj előre|menj előre|haladj előre)\b", re.IGNORECASE),
    "walk_backward": re.compile(r"\b(hátra|sétálj hátra|menj hátra|haladj hátra)\b", re.IGNORECASE),
    "turn_left": re.compile(r"\b(balra|fordulj balra|menj balra)\b", re.IGNORECASE),
    "turn_right": re.compile(r"\b(jobbra|fordulj jobbra|menj jobbra)\b", re.IGNORECASE),
    "stop": re.compile(r"\b(állj|megállj|állj meg|stop|vége|szünet)\b", re.IGNORECASE),
    "reset": re.compile(r"\b(újra|alaphelyzet|visszaállít|reset)\b", re.IGNORECASE),
    "follow_chair": re.compile(r"\b(kövesd a széket|keresd a széket|szék követése)\b", re.IGNORECASE),
    "stop_following": re.compile(r"\b(ne kövesd|állítsd le a követést|követés leállítása)\b", re.IGNORECASE),
}


class LocalVoiceController:
    def __init__(self, base_url: str = "http://127.0.0.1:8765", model_size: str = "tiny"):
        """
        Initializes the Voice Controller.
        - base_url: The simulator bridge URL.
        - model_size: Whisper model size ('tiny', 'base', 'small'). 'tiny' is recommended for Raspberry Pi.
        """
        self.client = HermesRobotClient(base_url=base_url)
        self.model_size = model_size
        self.recognizer = sr.Recognizer()
        
        # Adjust recognizer properties for better responsiveness
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8  # Wait 0.8s of silence before phrasing completes
        
        self.whisper_model = None

    def load_model(self):
        """Pre-loads the Whisper model locally to avoid latency on first command."""
        print(f"[*] Loading Whisper model '{self.model_size}' locally (Hungarian language configuration)...")
        # Under the hood, sr.recognize_whisper uses whisper.load_model
        self.whisper_model = whisper.load_model(self.model_size)
        print("[+] Local Whisper model loaded and ready.")

    async def execute_action(self, action: str) -> None:
        """Translates matched Hungarian patterns to robot commands."""
        print(f"\n[🚀] EXECUTING ACTION: {action.upper()}")
        try:
            if action == "walk_forward":
                res = await self.client.send_command(command="walk_forward", speed=0.3, turn=0.0, duration_sec=1.5)
                print(f"[✓] Move forward sent. Status: {res.status}")
            elif action == "walk_backward":
                res = await self.client.send_command(command="walk_backward", speed=0.3, turn=0.0, duration_sec=1.5)
                print(f"[✓] Move backward sent. Status: {res.status}")
            elif action == "turn_left":
                res = await self.client.send_command(command="turn_left", speed=0.0, turn=0.4, duration_sec=1.2)
                print(f"[✓] Turn left sent. Status: {res.status}")
            elif action == "turn_right":
                res = await self.client.send_command(command="turn_right", speed=0.0, turn=-0.4, duration_sec=1.2)
                print(f"[✓] Turn right sent. Status: {res.status}")
            elif action == "stop":
                res = await self.client.stop()
                print(f"[✓] Robot stopped. Status: {res.status}")
            elif action == "reset":
                res = await self.client.reset()
                print(f"[✓] Robot reset. Status: {res.status}")
            elif action == "follow_chair":
                config = FollowerConfigSchema(target_label="chair", follow_height=380.0)
                res = await self.client.start_following(config)
                print(f"[✓] Chair follower started: {res}")
            elif action == "stop_following":
                res = await self.client.stop_following()
                print(f"[✓] Chair follower stopped: {res}")
        except Exception as e:
            print(f"[!] Error executing action '{action}': {e}", file=sys.stderr)

    def parse_command(self, text: str) -> Optional[str]:
        """Parses speech text for any matching Hungarian command patterns."""
        cleaned_text = text.strip().lower()
        print(f"[🎤] Transcribed text: '{text}' (Cleaned: '{cleaned_text}')")
        
        for action, pattern in COMMAND_MAP.items():
            if pattern.search(cleaned_text):
                return action
        return None

    def listen_and_process_sync(self) -> Optional[str]:
        """Synchronously captures microphone audio and transcribes it locally."""
        with sr.Microphone() as source:
            print("\n[🎧] Calibrating microphone for ambient noise (1 second)...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
            print("[+] Microphone ready! Speak now (in Hungarian)...")
            
            try:
                # Capture audio stream
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=5)
                print("[*] Audio captured, transcribing offline using local Whisper...")
                
                # Transcribe using local Whisper model
                # Specifying language="hungarian" / "hu" ensures high accuracy
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

    async def start_voice_loop(self):
        """Asynchronous main loop for listening and commanding the robot."""
        # Ensure model is preloaded
        if self.whisper_model is None:
            self.load_model()
            
        print("\n=======================================================")
        print("   🦆 DUCK ROBOT LOCAL HUNGARIAN VOICE CONTROL NODE 🦆  ")
        print("=======================================================")
        print(f"Target Bridge: {self.client.base_url}")
        print(f"Whisper Model: {self.model_size}")
        print("Language:      Hungarian (Magyar)")
        print("Press Ctrl+C to terminate.")
        print("=======================================================")
        
        while True:
            # Run blocking mic input & Whisper transcription in an executor to avoid freezing the event loop
            loop = asyncio.get_running_loop()
            transcription = await loop.run_in_executor(None, self.listen_and_process_sync)
            
            if transcription:
                action = self.parse_command(transcription)
                if action:
                    await self.execute_action(action)
                else:
                    print("[?] Unknown command. Try: 'előre', 'hátra', 'balra', 'jobbra', 'állj', 'kövesd a széket'")
            
            # Short sleep before next listening phase
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Duck Robot Local Hungarian Voice Control Node")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8765", help="Bridge Server URL")
    parser.add_argument("--model", type=str, default="tiny", help="Whisper model: tiny, base, small")
    args = parser.parse_args()

    controller = LocalVoiceController(base_url=args.url, model_size=args.model)
    
    try:
        asyncio.run(controller.start_voice_loop())
    except KeyboardInterrupt:
        print("\n[!] Voice control terminated by user.")
        sys.exit(0)
