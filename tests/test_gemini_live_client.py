import asyncio
import os
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, mock_open

from duck_agent_sim.agent.gemini_live_client import GeminiLiveController
from duck_agent_sim.agent.agent_response import AgentResponse


@pytest.fixture
def mock_env():
    """Mock environment variable for testing."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-123"}):
        yield


class TestGeminiLiveControllerInit:
    """Tests correct initialization and API key resolution."""

    def test_init_with_env_key(self, mock_env):
        controller = GeminiLiveController(bridge_url="http://127.0.0.1:8765")
        assert controller.api_key == "test-key-123"
        assert "key=test-key-123" in controller.ws_uri

    def test_init_with_file_fallback(self):
        # Remove environment key to test fallback
        with patch.dict(os.environ, {}):
            with patch("os.path.exists", return_value=True):
                m = mock_open(read_data="GEMINI_API_KEY=file-key-456\n")
                with patch("builtins.open", m):
                    controller = GeminiLiveController()
                    assert controller.api_key == "file-key-456"

    def test_init_missing_key_raises_value_error(self):
        with patch.dict(os.environ, {}):
            with patch("os.path.exists", return_value=False):
                with pytest.raises(ValueError, match="Could not resolve GEMINI_API_KEY"):
                    GeminiLiveController()


class TestGeminiLiveSetupPayload:
    """Verifies the setup payload meets Google Gemini Multimodal Live API specifications."""

    def test_setup_payload_structure(self, mock_env):
        controller = GeminiLiveController(model="models/custom-model", voice_name="Fenrir")
        payload = controller._build_setup_payload()
        
        assert "setup" in payload
        setup = payload["setup"]
        assert setup["model"] == "models/custom-model"
        assert setup["generationConfig"]["responseModalities"] == ["AUDIO"]
        assert setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Fenrir"
        
        tools = setup["tools"][0]["functionDeclarations"]
        tool_names = [tool["name"] for tool in tools]
        assert "move_robot" in tool_names
        assert "follow_target" in tool_names
        assert "route_to_hermes" in tool_names


class TestGeminiLiveToolExecution:
    """Tests direct tool execution mapping to DirectController and HermesDelegator."""

    @pytest.mark.asyncio
    async def test_run_tool_move_robot(self, mock_env):
        controller = GeminiLiveController()
        controller.direct.execute = AsyncMock(
            return_value=AgentResponse(
                action="walk_forward",
                source="direct",
                success=True,
                speech="Előrehaladok.",
            )
        )

        args = {"command": "walk_forward", "speed": 0.5, "turn": 0.0, "duration_sec": 2.0}
        result = await controller._run_tool("move_robot", args)

        assert result["success"] is True
        assert result["speech"] == "Előrehaladok."
        assert result["action"] == "walk_forward"

        # Verify correct intent was built
        intent = controller.direct.execute.call_args[0][0]
        assert intent.action == "walk_forward"
        assert intent.route == "direct"
        assert intent.params["speed"] == 0.5
        assert intent.params["duration_sec"] == 2.0

    @pytest.mark.asyncio
    async def test_run_tool_follow_target(self, mock_env):
        controller = GeminiLiveController()
        controller.direct.execute = AsyncMock(
            return_value=AgentResponse(
                action="follow_target",
                source="direct",
                success=True,
                speech="Követem a széket.",
            )
        )

        args = {"target_label": "chair"}
        result = await controller._run_tool("follow_target", args)

        assert result["success"] is True
        assert result["speech"] == "Követem a széket."

        # Verify correct intent was built
        intent = controller.direct.execute.call_args[0][0]
        assert intent.action == "follow_target"
        assert intent.params["target_label"] == "chair"

    @pytest.mark.asyncio
    async def test_run_tool_route_to_hermes(self, mock_env):
        controller = GeminiLiveController()
        controller.hermes.delegate = AsyncMock(
            return_value=AgentResponse(
                action="hermes_chat",
                source="hermes",
                success=True,
                hermes_raw="Hiba kijavítva a schemas.py fájlban.",
                speech="Kész.",
            )
        )

        args = {"task": "fix schemas.py bug"}
        result = await controller._run_tool("route_to_hermes", args)

        assert result["success"] is True
        assert result["output"] == "Hiba kijavítva a schemas.py fájlban."
        assert result["speech"] == "Kész."

        controller.hermes.delegate.assert_awaited_once_with("fix schemas.py bug")


class TestGeminiLiveAudioFixes:
    """Verifies feedback prevention, mic gating, and interruption queue flushing."""

    @pytest.mark.asyncio
    async def test_interruption_flushes_queue(self, mock_env):
        controller = GeminiLiveController()
        controller.audio_output_queue.put_nowait(b"audio-1")
        controller.audio_output_queue.put_nowait(b"audio-2")
        controller.is_speaking = True
        controller._last_speaker_time = 999.0

        # Simulate receiving interrupted message
        ws_mock = AsyncMock()
        ws_mock.__aiter__.return_value = [
            json.dumps({
                "serverContent": {
                    "interrupted": True
                }
            })
        ]
        controller._ws = ws_mock
        controller._running = True

        # Run receiver loop (will stop when iterator ends)
        await controller._receive_loop()

        # The queue must be completely empty
        assert controller.audio_output_queue.empty()
        assert controller.is_speaking is False
        assert controller._last_speaker_time == 0.0

    def test_play_audio_loop_updates_speaking_state(self, mock_env):
        controller = GeminiLiveController()
        controller._speaker_stream = MagicMock()
        controller._playback_running = True
        
        # Put one chunk and then a None sentinel to break loop
        controller.audio_output_queue.put_nowait(b"dummy-pcm-data")
        controller.audio_output_queue.put_nowait(None)
        
        # Run play audio loop synchronously
        controller._play_audio_loop()
        
        # Verify that it wrote to the stream and reset is_speaking to False on finish
        controller._speaker_stream.write.assert_called_once_with(b"dummy-pcm-data")
        assert controller.is_speaking is False

    @pytest.mark.asyncio
    async def test_mic_loop_sends_silence_when_speaking(self, mock_env):
        import base64
        controller = GeminiLiveController()
        controller._ws = AsyncMock()
        controller._running = True
        controller.is_speaking = True # Active speaking state
        
        # Mock sounddevice raw input stream
        with patch("sounddevice.RawInputStream"):
            # Put raw data into input queue
            test_pcm = b"\x01\x02\x03\x04"
            await controller.audio_input_queue.put(test_pcm)
            
            # Start mic input loop and stop it immediately after processing
            async def stop_after_one_chunk():
                await asyncio.sleep(0.05)
                controller._running = False
                await controller.audio_input_queue.put(None)
                
            asyncio.create_task(stop_after_one_chunk())
            await controller._mic_input_loop()
            
            # Verify that the sent data was zeroed out (muted)
            controller._ws.send.assert_called()
            sent_payload = json.loads(controller._ws.send.call_args[0][0])
            sent_base64 = sent_payload["realtimeInput"]["mediaChunks"][0]["data"]
            sent_bytes = base64.b64decode(sent_base64)
            assert sent_bytes == b"\x00\x00\x00\x00"
