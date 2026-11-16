from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Source of "now", so the same code runs live and in a replay."""

    def now(self) -> datetime: ...

    def now_ms(self) -> int: ...

    async def sleep(self, seconds: float) -> None: ...
