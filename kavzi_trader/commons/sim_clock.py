from datetime import datetime

from kavzi_trader.commons.time_utility import milliseconds_to_datetime


class SimClock:
    """Simulated UTC time that only a replay driver moves, and only forward."""

    def __init__(self, start_ms: int) -> None:
        if start_ms < 0:
            raise ValueError(f"SimClock start must be >= 0 ms, got {start_ms}")
        self._now_ms = start_ms

    def now(self) -> datetime:
        return milliseconds_to_datetime(self._now_ms)

    def now_ms(self) -> int:
        return self._now_ms

    def advance_to(self, now_ms: int) -> None:
        if now_ms < self._now_ms:
            raise ValueError(
                f"SimClock cannot move backwards: {now_ms} < {self._now_ms}",
            )
        self._now_ms = now_ms
