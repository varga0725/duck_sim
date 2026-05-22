from pathlib import Path

from duck_agent_sim.schemas import (
    CommandResponse,
    ControlIntent,
    FollowerConfigSchema,
    HealthResponse,
    RobotCommand,
    SensorsState,
)


def test_phase3_final_report_exists_and_covers_required_sections():
    report = Path("docs/phase3_final_upstream_locomotion_alignment_report.md")

    assert report.exists()
    text = report.read_text()
    for phrase in (
        "Phase 3A",
        "ONNX contract status",
        "Observation contract status",
        "Actuator/default alignment status",
        "Command clamp consistency status",
        "Follower clamp",
        "Startup warning behavior",
        "Upstream adapter shadow-mode status",
        "Gemini/voice command arg status",
        "Warning-only",
        "Do not use on real robot",
        "Recommended Phase 4",
    ):
        assert phrase in text


def test_public_schema_stability_for_phase3_final():
    assert set(RobotCommand.model_json_schema()["properties"]) == {
        "command",
        "speed",
        "turn",
        "duration_sec",
        "safety",
    }
    assert set(ControlIntent.model_json_schema()["properties"]) == {
        "linear_x",
        "linear_y",
        "yaw",
    }
    assert set(CommandResponse.model_json_schema()["properties"]) == {
        "accepted",
        "command",
        "mapped_control",
        "state",
        "safety_intervention",
        "safety_reasons",
    }
    assert set(HealthResponse.model_json_schema()["properties"]) == {
        "status",
        "sim_mode",
        "robot",
    }
    assert "imu" in SensorsState.model_json_schema()["properties"]
    assert "max_speed" in FollowerConfigSchema.model_json_schema()["properties"]
