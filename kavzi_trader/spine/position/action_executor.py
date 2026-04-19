import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.api.common.models import (
    OrderResponseSchema,
    OrderSide,
    OrderType,
)
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.schemas import OpenOrderSchema, PositionSchema

logger = logging.getLogger(__name__)

_STOP_ORDER_TYPES = frozenset(
    {OrderType.STOP, OrderType.STOP_MARKET},
)

# Binance futures error code for "Unknown order sent" — returned when the order
# is no longer on the exchange (already filled, cancelled, or never existed).
# Safe to treat as a successful removal from the local side.
_ERROR_CODE_UNKNOWN_ORDER = -2011


class PositionActionExecutor:
    def __init__(
        self,
        exchange: BinanceClient,
        state_manager: StateManager,
    ) -> None:
        self._exchange = exchange
        self._state = state_manager

    async def execute(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> Decimal | None:
        """Execute action and return exit price for FULL_EXIT, None otherwise."""
        if action.action == PositionActionType.NO_ACTION:
            return None
        if action.action == PositionActionType.MOVE_STOP_LOSS:
            await self._move_stop_loss(position, action)
            return None
        if action.action == PositionActionType.PARTIAL_EXIT:
            await self._partial_exit(position, action)
            return None
        # PositionActionType.FULL_EXIT
        return await self._full_exit(position)

    async def _move_stop_loss(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> None:
        if action.new_stop_loss is None:
            return

        # Snapshot existing stop orders BEFORE placing the new one so the
        # cancel step targets only pre-existing stops and cannot accidentally
        # cancel the freshly placed replacement (which also links to this
        # position id).
        linked = await self._state.orders.get_by_position(position.id)
        old_stop_orders = [
            order for order in linked if order.order_type in _STOP_ORDER_TYPES
        ]

        try:
            await self._place_stop_order(
                position,
                action.new_stop_loss,
                position.quantity,
            )
        except Exception:
            logger.exception(
                "Failed to place new stop order for %s; "
                "leaving existing stop orders in place",
                position.symbol,
                extra={
                    "position_id": position.id,
                    "symbol": position.symbol,
                    "new_stop_loss": str(action.new_stop_loss),
                },
            )
            return

        for order in old_stop_orders:
            await self._cancel_order(position, order)

    async def _partial_exit(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> None:
        if action.exit_quantity is None:
            return
        exit_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        try:
            await self._exchange.create_order(
                symbol=position.symbol,
                side=exit_side,
                order_type=OrderType.MARKET,
                quantity=action.exit_quantity,
                reduce_only=True,
            )
        except Exception:
            logger.exception(
                "Failed to submit partial-exit order for %s",
                position.symbol,
                extra={
                    "position_id": position.id,
                    "symbol": position.symbol,
                    "exit_quantity": str(action.exit_quantity),
                },
            )
            return

        # Persist partial_exit_done=True BEFORE cancelling linked orders and
        # re-placing stops/TPs. If any of those fail, the flag is already
        # durable and the next tick will not re-submit a partial exit against
        # a position that has already been reduced on the exchange.
        updated_position = position.model_copy(update={"partial_exit_done": True})
        try:
            await self._state.update_position(updated_position)
        except Exception:
            logger.critical(
                "Partial exit executed on exchange for %s but failed to persist "
                "partial_exit_done flag; reconciliation required",
                position.symbol,
                extra={
                    "position_id": position.id,
                    "symbol": position.symbol,
                    "exit_quantity": str(action.exit_quantity),
                    "needs_reconciliation": True,
                },
                exc_info=True,
            )
            return

        await self._cancel_linked_orders(updated_position)
        remaining = updated_position.quantity - action.exit_quantity
        if remaining > 0:
            await self._place_stop_order(
                updated_position,
                updated_position.current_stop_loss,
                remaining,
            )
            await self._place_take_profit_order(
                updated_position,
                updated_position.take_profit,
                remaining,
            )

    async def _full_exit(self, position: PositionSchema) -> Decimal | None:
        exit_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        try:
            order_response = await self._exchange.create_order(
                symbol=position.symbol,
                side=exit_side,
                order_type=OrderType.MARKET,
                quantity=position.quantity,
                reduce_only=True,
            )
        except Exception:
            logger.exception(
                "Failed to submit full-exit order for %s; "
                "position left for reconciliation",
                position.symbol,
                extra={"position_id": position.id},
            )
            return None
        await self._cancel_linked_orders(position)
        await self._state.remove_position(position.id)
        return order_response.price

    async def _cancel_linked_orders(self, position: PositionSchema) -> None:
        linked = await self._state.orders.get_by_position(position.id)
        for order in linked:
            await self._cancel_order(position, order)

    async def _cancel_order(
        self,
        position: PositionSchema,
        order: OpenOrderSchema,
    ) -> None:
        """
        Cancel a single linked order on the exchange and remove it locally.

        Local removal only runs on the success path, with one exception:
        a Binance ``-2011`` ("Unknown order sent") response means the order
        is already gone from the exchange (filled or cancelled elsewhere),
        so purging local state is correct. For any other failure we keep
        the local record so reconciliation can reason about the mismatch.
        """
        try:
            await self._exchange.cancel_order(
                symbol=position.symbol,
                order_id=int(order.order_id),
            )
        except ExchangeError as exc:
            if exc.code == _ERROR_CODE_UNKNOWN_ORDER:
                logger.info(
                    "Order %s already absent on exchange for position %s; "
                    "removing from local state",
                    order.order_id,
                    position.id,
                )
                await self._state.remove_order(order.order_id)
                return
            logger.exception(
                "Failed to cancel linked order %s for position %s; "
                "keeping local record for reconciliation",
                order.order_id,
                position.id,
            )
            return
        except Exception:
            logger.exception(
                "Failed to cancel linked order %s for position %s; "
                "keeping local record for reconciliation",
                order.order_id,
                position.id,
            )
            return
        await self._state.remove_order(order.order_id)

    async def _place_stop_order(
        self,
        position: PositionSchema,
        stop_loss: Decimal,
        quantity: Decimal,
    ) -> None:
        stop_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        response = await self._exchange.create_order(
            symbol=position.symbol,
            side=stop_side,
            order_type=OrderType.STOP_MARKET,
            quantity=quantity,
            stop_price=stop_loss,
            reduce_only=True,
        )
        await self._save_linked_order(response, position.id)

    async def _place_take_profit_order(
        self,
        position: PositionSchema,
        take_profit: Decimal,
        quantity: Decimal,
    ) -> None:
        tp_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        response = await self._exchange.create_order(
            symbol=position.symbol,
            side=tp_side,
            order_type=OrderType.TAKE_PROFIT_MARKET,
            quantity=quantity,
            stop_price=take_profit,
            reduce_only=True,
        )
        await self._save_linked_order(response, position.id)

    async def _save_linked_order(
        self,
        order: OrderResponseSchema,
        position_id: str,
    ) -> None:
        created_at = order.time or utc_now()
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
            created_at=created_at,
        )
        await self._state.save_order(open_order)
