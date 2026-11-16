import logging
from collections.abc import Awaitable
from datetime import datetime
from decimal import Decimal

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
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.order_enums import OrderSide, OrderType, TimeInForce
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.spine.precision.symbol_precision import (
    OrderPrecisionError,
    SymbolPrecision,
)

logger = logging.getLogger(__name__)

_STOP_TYPES = frozenset({OrderType.STOP, OrderType.STOP_MARKET})
_TAKE_PROFIT_TYPES = frozenset(
    {OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_MARKET},
)


class PrecisionExchangeClient:
    """Rounds every outgoing order to exchange filters before it is sent.

    One choke point for entries, protective legs, partial exits and rebalances,
    live and paper alike. Everything except create_order is passed through.
    """

    def __init__(self, inner: ExchangeClient, precision: SymbolPrecision) -> None:
        self._inner = inner
        self._precision = precision

    async def create_order(
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
    ) -> OrderResponseSchema:
        precision = self._precision
        if price is not None:
            # Never pay more on a buy or receive less on a sell than planned.
            price = precision.round_price(
                symbol,
                price,
                "DOWN" if side == OrderSide.BUY else "UP",
            )
        if stop_price is not None:
            stop_price = self._round_trigger(symbol, side, order_type, stop_price)
        if quantity is not None:
            market = order_type == OrderType.MARKET
            rounded = precision.round_qty(symbol, quantity, market=market)
            reason = precision.check_qty(
                symbol,
                rounded,
                price,
                market=market,
                reduce_only=reduce_only,
            )
            if reason is not None:
                raise OrderPrecisionError(
                    f"{order_type.value} {side.value} {symbol} not sent: {reason}",
                )
            if rounded != quantity:
                logger.info(
                    "Rounded %s %s quantity %s -> %s",
                    symbol,
                    order_type.value,
                    quantity,
                    rounded,
                    extra={"symbol": symbol},
                )
            quantity = rounded
        return await self._inner.create_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
            stop_price=stop_price,
            reduce_only=reduce_only,
        )

    def _round_trigger(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        stop_price: Decimal,
    ) -> Decimal:
        # An exit order's side is opposite the position: SELL closes a long.
        closes_long = side == OrderSide.SELL
        if order_type in _STOP_TYPES:
            return self._precision.round_stop_loss(
                symbol,
                stop_price,
                is_long=closes_long,
            )
        if order_type in _TAKE_PROFIT_TYPES:
            return self._precision.round_take_profit(
                symbol,
                stop_price,
                is_long=closes_long,
            )
        return self._precision.round_price(symbol, stop_price, "DOWN")

    def get_ticker(self, symbol: str) -> Awaitable[TickerSchema]:
        return self._inner.get_ticker(symbol)

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
        limit: int = 500,
    ) -> Awaitable[list[CandlestickSchema]]:
        return self._inner.get_klines(symbol, interval, start_time, end_time, limit)

    def get_funding_rate(
        self,
        symbol: str,
        limit: int = 100,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> Awaitable[list[FundingRateDict]]:
        return self._inner.get_funding_rate(symbol, limit, start_time, end_time)

    def get_open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> Awaitable[list[OpenInterestHistDict]]:
        return self._inner.get_open_interest_history(
            symbol, period, limit, start_time, end_time
        )

    def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> Awaitable[list[LongShortRatioDict]]:
        return self._inner.get_long_short_ratio(
            symbol, period, limit, start_time, end_time
        )

    def get_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> Awaitable[OrderResponseSchema]:
        return self._inner.get_order(symbol, order_id, client_order_id)

    def cancel_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> Awaitable[OrderResponseSchema]:
        return self._inner.cancel_order(symbol, order_id, client_order_id)

    def get_open_orders(
        self,
        symbol: str | None = None,
    ) -> Awaitable[list[OrderResponseSchema]]:
        return self._inner.get_open_orders(symbol)

    def get_account_info(self) -> Awaitable[AccountInfoDict]:
        return self._inner.get_account_info()

    def futures_change_leverage(
        self,
        symbol: str,
        leverage: int,
    ) -> Awaitable[LeverageChangeDict]:
        return self._inner.futures_change_leverage(symbol, leverage)

    def futures_change_margin_type(
        self,
        symbol: str,
        margin_type: str,
    ) -> Awaitable[MarginTypeChangeDict | None]:
        return self._inner.futures_change_margin_type(symbol, margin_type)

    def futures_get_position_info(
        self,
        symbol: str | None = None,
    ) -> Awaitable[list[PositionInfoDict]]:
        return self._inner.futures_get_position_info(symbol)

    def futures_get_leverage_brackets(
        self,
        symbol: str | None = None,
    ) -> Awaitable[list[LeverageBracketDict]]:
        return self._inner.futures_get_leverage_brackets(symbol)

    def close(self) -> Awaitable[None]:
        return self._inner.close()
