import logging
from decimal import Decimal

from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.domain.order_enums import OrderStatus, OrderType
from kavzi_trader.domain.state_schemas import OpenOrderSchema, PositionSchema
from kavzi_trader.spine.position.exchange_close_schema import ExchangeCloseSchema
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)

_CLOSE_REASON_BY_ORDER_TYPE = {
    OrderType.STOP_MARKET: "stop_loss_filled",
    OrderType.STOP: "stop_loss_filled",
    OrderType.TAKE_PROFIT_MARKET: "take_profit_filled",
    OrderType.TAKE_PROFIT: "take_profit_filled",
}
_POSITION_GONE_REASON = "exchange_position_closed"


class ExchangeFillDetector:
    """Finds positions the exchange closed through their SL/TP orders."""

    def __init__(self, exchange: ExchangeClient, state_manager: StateManager) -> None:
        self._exchange = exchange
        self._state = state_manager

    async def detect(self, position: PositionSchema) -> ExchangeCloseSchema | None:
        """Return the exchange-side close of this position, or None if still open."""
        linked = await self._state.orders.get_by_position(position.id)
        for order in linked:
            reason = _CLOSE_REASON_BY_ORDER_TYPE.get(order.order_type)
            if reason is None:
                continue
            exit_price = await self._filled_price(position, order)
            if exit_price is not None:
                return ExchangeCloseSchema(close_reason=reason, exit_price=exit_price)

        # No protective leg filled; the position may still have been closed
        # some other way (manual close, liquidation, expired legs).
        if await self._is_flat_on_exchange(position.symbol):
            return ExchangeCloseSchema(close_reason=_POSITION_GONE_REASON)
        return None

    async def _filled_price(
        self,
        position: PositionSchema,
        order: OpenOrderSchema,
    ) -> Decimal | None:
        try:
            response = await self._exchange.get_order(
                symbol=position.symbol,
                order_id=int(order.order_id),
            )
        except ExchangeError:
            logger.warning(
                "Could not look up protective order %s for position %s",
                order.order_id,
                position.id,
                extra={"position_id": position.id, "order_id": order.order_id},
                exc_info=True,
            )
            return None
        if response.status != OrderStatus.FILLED:
            return None
        # A fill without any reported price still means closed; use the trigger.
        return response.effective_fill_price or response.stop_price or order.price

    async def _is_flat_on_exchange(self, symbol: str) -> bool:
        rows = await self._exchange.futures_get_position_info(symbol)
        # positionRisk v3 (and the paper client) omit flat symbols: empty == flat.
        open_amount = sum(
            (abs(Decimal(str(row["positionAmt"]))) for row in rows),
            Decimal(0),
        )
        return open_amount == 0
