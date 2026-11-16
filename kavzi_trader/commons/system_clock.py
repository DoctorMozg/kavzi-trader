import asyncio
from datetime import UTC, datetime


class SystemClock:
    """Wall-clock time in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def now_ms(self) -> int:
        return int(self.now().timestamp() * 1000)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


SYSTEM_CLOCK = SystemClock()
