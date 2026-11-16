from collections.abc import Awaitable
from datetime import datetime
from typing import Protocol

from kavzi_trader.api.binance.schemas.data_dicts import (
    FundingRateDict,
    LongShortRatioDict,
    OpenInterestHistDict,
)


class OrderFlowSource(Protocol):
    """The exchange reads the order-flow fetcher makes: live Binance or a replay."""

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
