from datetime import UTC, datetime


class SystemClock:
    """Wall-clock time in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def now_ms(self) -> int:
        return int(self.now().timestamp() * 1000)


SYSTEM_CLOCK = SystemClock()
