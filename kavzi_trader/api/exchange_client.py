from collections.abc import Awaitable
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from kavzi_trader.api.binance.schemas.data_dicts import (
    AccountInfoDict,
    FundingRateDict,
    LeverageBracketDict,
    LeverageChangeDict,
    LongShortRatioDict,
    MarginTypeChangeDict,
    OpenInterestHistDict,
    PositionInfoDict,
)
from kavzi_trader.api.common.models import TickerSchema
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.order_enums import OrderSide, OrderType, TimeInForce
from kavzi_trader.domain.order_response import OrderResponseSchema

# Methods return Awaitable rather than being declared async because
# BinanceClient wraps its coroutines in an error-mapping decorator.


class ExchangeClient(Protocol):
    """The exchange calls the spine, orchestrator and paper trading rely on.

    BinanceClient and PaperExchangeClient both satisfy it structurally.
    """

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

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        time_in_force: TimeInForce | None = None,
        client_order_id: str | None = None,
        stop_price: Decimal | None = None,
        reduce_only: bool = False,
    ) -> Awaitable[OrderResponseSchema]: ...

    def get_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> Awaitable[OrderResponseSchema]: ...

    def cancel_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> Awaitable[OrderResponseSchema]: ...

    def get_open_orders(
        self,
        symbol: str | None = None,
    ) -> Awaitable[list[OrderResponseSchema]]: ...

    def get_account_info(self) -> Awaitable[AccountInfoDict]: ...

    def futures_change_leverage(
        self,
        symbol: str,
        leverage: int,
    ) -> Awaitable[LeverageChangeDict]: ...

    def futures_change_margin_type(
        self,
        symbol: str,
        margin_type: str,
    ) -> Awaitable[MarginTypeChangeDict | None]: ...

    def futures_get_position_info(
        self,
        symbol: str | None = None,
    ) -> Awaitable[list[PositionInfoDict]]: ...

    def futures_get_leverage_brackets(
        self,
        symbol: str | None = None,
    ) -> Awaitable[list[LeverageBracketDict]]: ...

    def close(self) -> Awaitable[None]: ...
