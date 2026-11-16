from collections.abc import Awaitable
from datetime import datetime
from typing import Protocol

from kavzi_trader.api.binance.schemas.data_dicts import (
    FundingRateDict,
    LongShortRatioDict,
    OpenInterestHistDict,
)
from kavzi_trader.api.common.models import TickerSchema
from kavzi_trader.domain.candlestick import CandlestickSchema


class MarketFeed(Protocol):
    """Market data the paper exchange prices against: live Binance or a replay."""

    # Awaitable, not async def: BinanceClient's retry-decorated methods return one.
    def get_ticker(self, symbol: str) -> Awaitable[TickerSchema]: ...

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
        limit: int = 500,
    ) -> Awaitable[list[CandlestickSchema]]: ...

    def get_funding_rate(
        self,
        symbol: str,
        limit: int = 100,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> Awaitable[list[FundingRateDict]]: ...

    def get_open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> Awaitable[list[OpenInterestHistDict]]: ...

    def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> Awaitable[list[LongShortRatioDict]]: ...

    def close(self) -> Awaitable[None]: ...
