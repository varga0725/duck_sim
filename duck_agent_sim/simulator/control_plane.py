import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from duck_agent_sim.schemas import ControlIntent, RobotCommand


ZERO_CONTROL = ControlIntent(linear_x=0.0, linear_y=0.0, yaw=0.0)


@dataclass(frozen=True)
class DesiredMotionState:
    command: str
    control: ControlIntent
    safety: object
    started_at: float
    expires_at: Optional[float]
    request_id: Optional[str] = None

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and time.monotonic() >= self.expires_at


class CommandExecutionCancelled(asyncio.CancelledError):
    pass


def command_duration(command: RobotCommand) -> float:
    if command.command in ("stop", "reset"):
        return 0.0
    return float(command.duration_sec)
