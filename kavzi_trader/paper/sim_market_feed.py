from datetime import datetime
from decimal import Decimal

from kavzi_trader.api.binance.schemas.data_dicts import (
    FundingRateDict,
    LongShortRatioDict,
    OpenInterestHistDict,
)
from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.api.common.models import TickerSchema
from kavzi_trader.domain.candlestick import CandlestickSchema


class SimMarketFeed:
    """Prices set by a replay driver or a test; it serves no history."""

    def __init__(self) -> None:
        self._prices: dict[str, Decimal] = {}

    def set_price(self, symbol: str, price: Decimal) -> None:
        if price <= 0:
            raise ValueError(f"Price for {symbol} must be positive, got {price}")
        self._prices[symbol] = price

    async def get_ticker(self, symbol: str) -> TickerSchema:
        price = self._prices.get(symbol)
        if price is None:
            raise ExchangeError(f"No simulated price for {symbol}")
        return TickerSchema(symbol=symbol, last_price=price)

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
        limit: int = 500,
    ) -> list[CandlestickSchema]:
        raise NotImplementedError(f"SimMarketFeed has no {interval} klines")

    async def get_funding_rate(
        self,
        symbol: str,
        limit: int = 100,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[FundingRateDict]:
        raise NotImplementedError(f"SimMarketFeed has no funding history for {symbol}")

    async def get_open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[OpenInterestHistDict]:
        raise NotImplementedError(f"SimMarketFeed has no open interest for {symbol}")

    async def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[LongShortRatioDict]:
        raise NotImplementedError(f"SimMarketFeed has no long/short ratio for {symbol}")

    async def close(self) -> None:
        return None
