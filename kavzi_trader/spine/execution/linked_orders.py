import logging

from kavzi_trader.api.common.exceptions import (
    UNKNOWN_ORDER_ERROR_CODE,
    ExchangeError,
)
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.domain.state_schemas import OpenOrderSchema, PositionSchema
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class LinkedOrderService:
    """Tracks exchange orders in state and cancels those tied to a position."""

    def __init__(
        self,
        exchange: ExchangeClient,
        state_manager: StateManager,
    ) -> None:
        self._exchange = exchange
        self._state = state_manager

    async def save(
        self,
        order: OrderResponseSchema,
        position_id: str | None = None,
    ) -> None:
        open_order = OpenOrderSchema(
            order_id=str(order.order_id),
            symbol=order.symbol,
            side=order.side,
            order_type=order.type,
            price=order.price,
            quantity=order.orig_qty,
            executed_qty=order.executed_qty,
            status=order.status,
            linked_position_id=position_id,
            created_at=order.time or utc_now(),
        )
        await self._state.save_order(open_order)

    async def cancel_for_position(self, position: PositionSchema) -> None:
        linked = await self._state.orders.get_by_position(position.id)
        for order in linked:
            await self.cancel(order)

    async def cancel(self, order: OpenOrderSchema) -> None:
        """Cancel one order on the exchange and drop its local record.

        Binance -2011 (unknown order) means it is already gone, so the record
        is purged. Any other failure keeps the record so a later sweep retries.
        """
        try:
            await self._exchange.cancel_order(
                symbol=order.symbol,
                order_id=int(order.order_id),
            )
        except Exception as exc:
            if not (
                isinstance(exc, ExchangeError) and exc.code == UNKNOWN_ORDER_ERROR_CODE
            ):
                logger.exception(
                    "Failed to cancel linked order %s for position %s; "
                    "keeping local record for retry",
                    order.order_id,
                    order.linked_position_id,
                )
                return
            logger.info(
                "Order %s already absent on exchange for position %s; "
                "removing from local state",
                order.order_id,
                order.linked_position_id,
            )
        await self._state.remove_order(order.order_id)
