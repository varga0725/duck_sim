import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ClockTelemetry:
    name: str
    fixed_dt_sec: float
    tick_count: int
    drift_sec: float
    max_drift_sec: float
    overruns: int


class SimulationClock:
    """Monotonic fixed-step loop pacing and drift telemetry."""

    def __init__(self, name: str, fixed_dt_sec: float):
        if fixed_dt_sec <= 0.0:
            raise ValueError("fixed_dt_sec must be positive")
        self.name = name
        self.fixed_dt_sec = fixed_dt_sec
        self._next_tick = time.monotonic()
        self._tick_count = 0
        self._drift_sec = 0.0
        self._max_drift_sec = 0.0
        self._overruns = 0

    def reset(self) -> None:
        self._next_tick = time.monotonic()
        self._tick_count = 0
        self._drift_sec = 0.0
        self._max_drift_sec = 0.0
        self._overruns = 0

    def sleep_until_next_tick(self) -> float:
        now = time.monotonic()
        sleep_sec = self._next_tick - now
        if sleep_sec > 0.0:
            time.sleep(sleep_sec)
            now = time.monotonic()
        else:
            self._overruns += 1

        self._drift_sec = now - self._next_tick
        self._max_drift_sec = max(self._max_drift_sec, abs(self._drift_sec))
        self._next_tick += self.fixed_dt_sec
        self._tick_count += 1
        return self.fixed_dt_sec

    def telemetry(self) -> ClockTelemetry:
        return ClockTelemetry(
            name=self.name,
            fixed_dt_sec=self.fixed_dt_sec,
            tick_count=self._tick_count,
            drift_sec=self._drift_sec,
            max_drift_sec=self._max_drift_sec,
            overruns=self._overruns,
        )
