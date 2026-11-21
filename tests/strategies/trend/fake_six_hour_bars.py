import numpy as np

from kavzi_trader.strategies.trend.intraday_closes_schema import (
    IntradayClosesSchema,
)
from tests.strategies.trend.conftest import BASE_MS

SIX_HOURS_MS = 6 * 3_600_000
DAY_MS = 4 * SIX_HOURS_MS


class SixHourMarket:
    """6h closes from BASE_MS, four per day; day i closes with bar 4i + 3."""

    def __init__(self, bars: dict[str, np.ndarray]) -> None:
        self.bars = bars
        self.unpublished = 0  # newest closed bars the exchange has not served yet
        self.daily = _DailyCloses(self)
        self.intraday = _SixHourCloses(self)


class _DailyCloses:
    def __init__(self, market: SixHourMarket) -> None:
        self._market = market

    async def closes(self, symbol: str, days: int, now_ms: int) -> np.ndarray:
        closed = (now_ms - BASE_MS) // DAY_MS
        return self._market.bars[symbol][3::4][:closed][-days:]


class _SixHourCloses:
    def __init__(self, market: SixHourMarket) -> None:
        self._market = market

    async def closes(
        self, symbol: str, count: int, now_ms: int
    ) -> IntradayClosesSchema:
        end = (now_ms - BASE_MS) // SIX_HOURS_MS - self._market.unpublished
        start = max(0, end - count)
        return IntradayClosesSchema(
            open_time_ms=[BASE_MS + i * SIX_HOURS_MS for i in range(start, end)],
            closes=self._market.bars[symbol][start:end].tolist(),
        )
