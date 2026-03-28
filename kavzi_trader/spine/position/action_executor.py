import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
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
        await self._cancel_linked_stop_orders(position)
        await self._place_stop_order(
            position,
            action.new_stop_loss,
            position.quantity,
        )

    async def _partial_exit(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> None:
        if action.exit_quantity is None:
            return
        exit_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        await self._exchange.create_order(
            symbol=position.symbol,
            side=exit_side,
            order_type=OrderType.MARKET,
            quantity=action.exit_quantity,
            reduce_only=True,
        )
        await self._cancel_linked_orders(position)
        remaining = position.quantity - action.exit_quantity
        if remaining > 0:
            await self._place_stop_order(
                position,
                position.current_stop_loss,
                remaining,
            )
            await self._place_take_profit_order(
                position,
                position.take_profit,
                remaining,
            )

    async def _full_exit(self, position: PositionSchema) -> Decimal:
        exit_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        order_response = await self._exchange.create_order(
            symbol=position.symbol,
            side=exit_side,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            reduce_only=True,
        )
        await self._cancel_linked_orders(position)
        await self._state.remove_position(position.id)
        return order_response.price

    async def _cancel_linked_orders(self, position: PositionSchema) -> None:
        linked = await self._state.orders.get_by_position(position.id)
        for order in linked:
            try:
                await self._exchange.cancel_order(
                    symbol=position.symbol,
                    order_id=int(order.order_id),
                )
            except Exception:
                logger.exception(
                    "Failed to cancel linked order %s for position %s",
                    order.order_id,
                    position.id,
                )
            await self._state.remove_order(order.order_id)

    async def _cancel_linked_stop_orders(
        self,
        position: PositionSchema,
    ) -> None:
        linked = await self._state.orders.get_by_position(position.id)
        for order in linked:
            if order.order_type not in _STOP_ORDER_TYPES:
                continue
            try:
                await self._exchange.cancel_order(
                    symbol=position.symbol,
                    order_id=int(order.order_id),
                )
            except Exception:
                logger.exception(
                    "Failed to cancel stop order %s for position %s",
                    order.order_id,
                    position.id,
                )
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
