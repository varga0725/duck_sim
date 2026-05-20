"""
Unified response envelope for DuckAgent actions.

Every action — whether handled directly or delegated to Hermes — returns an
AgentResponse so callers (voice loop, CLI, future web UI) get a single,
predictable shape.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from duck_agent_sim.schemas import RobotState


class AgentResponse(BaseModel):
    """Unified response returned by DuckAgent for every processed input."""

    action: str = Field(
        ...,
        description="Semantic action key, e.g. 'walk_forward', 'hermes_chat', 'follow_target'.",
    )
    source: Literal["direct", "hermes"] = Field(
        ...,
        description="Which subsystem produced the response.",
    )
    robot_state: Optional[RobotState] = Field(
        default=None,
        description="Robot state snapshot after execution (present for motor commands).",
    )
    speech: Optional[str] = Field(
        default=None,
        description="Text to be spoken aloud via TTS.",
    )
    hermes_raw: Optional[str] = Field(
        default=None,
        description="Raw text returned by Hermes when the request was delegated.",
    )
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Wall-clock processing time in milliseconds.",
    )
    success: bool = Field(
        default=True,
        description="Whether the action completed without errors.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Human-readable error message when success is False.",
    )
