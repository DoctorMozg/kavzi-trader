from typing import Protocol

from kavzi_trader.strategies.trend.intraday_closes_schema import (
    IntradayClosesSchema,
)


class IntradayCloseProvider(Protocol):
    """Supplies the newest ``count`` closed intraday bars, oldest first."""

    async def closes(
        self, symbol: str, count: int, now_ms: int
    ) -> IntradayClosesSchema: ...
