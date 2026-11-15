from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.binance.schemas.data_dicts import (
    FundingRateDict,
    OpenInterestHistDict,
)
from kavzi_trader.domain.candlestick import CandlestickSchema

SETTLE_MS = 8 * 3600 * 1000
OI_STEP_MS = 15 * 60 * 1000


def settlement_rate(ms: int) -> float:
    return 0.0001 * (1 + (ms // SETTLE_MS) % 5)


def open_interest(ms: int) -> float:
    return 1000.0 + (ms // OI_STEP_MS) % 7


class FakeExchange:
    """Serves klines, 8h funding and 15m OI histories in pages, like Binance does.

    As on Binance, OI without an end time returns the latest rows.
    """

    def __init__(self, now_ms: int) -> None:
        self.now_ms = now_ms
        self.funding_calls: list[tuple[int, int, int]] = []
        self.oi_calls: list[tuple[int, int | None, int]] = []
        self.kline_calls: list[tuple[str, int, int]] = []

    async def get_klines(
        self, symbol: str, interval: str, start_time: int, end_time: int, limit: int
    ) -> list[CandlestickSchema]:
        self.kline_calls.append((interval, start_time, end_time))
        step_ms = KLINE_INTERVALS[interval] * 1000
        first = start_time + (-start_time) % step_ms
        last = min(end_time, self.now_ms - step_ms)
        return [_candle(t, step_ms) for t in range(first, last + 1, step_ms)][:limit]

    async def get_funding_rate(
        self, symbol: str, limit: int, start_time: int, end_time: int
    ) -> list[FundingRateDict]:
        self.funding_calls.append((start_time, end_time, limit))
        first = start_time + (-start_time) % SETTLE_MS
        times = list(range(first, end_time + 1, SETTLE_MS))[:limit]
        return [
            FundingRateDict(
                symbol=symbol, fundingRate=str(settlement_rate(t)), fundingTime=t
            )
            for t in times
        ]

    async def get_open_interest_history(
        self,
        symbol: str,
        period: str,
        limit: int,
        start_time: int,
        end_time: int | None = None,
    ) -> list[OpenInterestHistDict]:
        self.oi_calls.append((start_time, end_time, limit))
        first = start_time + (-start_time) % OI_STEP_MS
        last = min(self.now_ms, self.now_ms if end_time is None else end_time)
        times = list(range(first, last + 1, OI_STEP_MS))
        times = times[-limit:] if end_time is None else times[:limit]
        return [
            OpenInterestHistDict(
                symbol=symbol,
                sumOpenInterest=str(open_interest(t)),
                sumOpenInterestValue="0",
                timestamp=t,
            )
            for t in times
        ]


def _candle(open_ms: int, step_ms: int) -> CandlestickSchema:
    price = Decimal(100 + (open_ms // step_ms) % 9)
    return CandlestickSchema(
        open_time=datetime.fromtimestamp(open_ms / 1000, UTC),
        open_price=price,
        high_price=price + 1,
        low_price=price - 1,
        close_price=price,
        volume=Decimal(10),
        close_time=datetime.fromtimestamp((open_ms + step_ms - 1) / 1000, UTC),
        quote_volume=Decimal(1000),
        trades_count=5,
        taker_buy_base_volume=Decimal(5),
        taker_buy_quote_volume=Decimal(500),
    )
