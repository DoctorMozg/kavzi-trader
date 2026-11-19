from typing import Protocol

from kavzi_trader.strategies.trend.hourly_variance_schema import HourlyVarianceSchema


class HourlyVarianceProvider(Protocol):
    """Supplies complete hours in [start_ms, end_ms), oldest first."""

    async def hours(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> list[HourlyVarianceSchema]: ...
