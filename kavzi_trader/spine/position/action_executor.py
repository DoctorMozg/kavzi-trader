import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.order_enums import OrderSide, OrderType
from kavzi_trader.domain.position_action import PositionActionSchema
from kavzi_trader.domain.position_action_type import PositionActionType
from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.spine.execution.linked_orders import LinkedOrderService
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)

_TAKE_PROFIT_ORDER_TYPES = frozenset(
    {OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_MARKET},
)


class PositionActionExecutor:
    def __init__(
        self,
        exchange: BinanceClient,
        state_manager: StateManager,
    ) -> None:
        self._exchange = exchange
        self._state = state_manager
        self._linked_orders = LinkedOrderService(exchange, state_manager)

    async def execute(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> Decimal | None:
        """Execute action; the executor is the sole writer of position state.

        Returns the fill price for FULL_EXIT, None otherwise or when unknown.
        """
        if action.action == PositionActionType.NO_ACTION:
            return None
        if action.action == PositionActionType.PARTIAL_EXIT:
            await self._partial_exit(position, action)
            return None
        # PositionActionType.FULL_EXIT
        return await self._full_exit(position)

    async def close_after_exchange_fill(self, position: PositionSchema) -> None:
        """Drop a position the exchange already closed, with its surviving orders."""
        await self._linked_orders.cancel_for_position(position)
        await self._state.remove_position(position.id)

    async def sweep_orphaned_orders(self) -> None:
        """Cancel linked orders whose position is gone, e.g. after a failed cancel."""
        # Orders are read before positions: a position is always saved before its
        # protective orders, so any order seen here has an owner in the later read.
        orders = await self._state.get_open_orders()
        live_ids = {p.id for p in await self._state.get_all_positions()}
        for order in orders:
            owner = order.linked_position_id
            if owner is not None and owner not in live_ids:
                logger.warning(
                    "Cancelling orphaned order %s of closed position %s",
                    order.order_id,
                    owner,
                    extra={"order_id": order.order_id, "position_id": owner},
                )
                await self._linked_orders.cancel(order)

    async def retry_missing_take_profit(self, position: PositionSchema) -> None:
        """Place the TP of a half-bracketed position unless one already exists."""
        linked = await self._state.orders.get_by_position(position.id)
        if any(o.order_type in _TAKE_PROFIT_ORDER_TYPES for o in linked):
            return
        # The earlier attempt may have reached the exchange and only failed to save.
        exit_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        for resting in await self._exchange.get_open_orders(position.symbol):
            if (
                resting.type in _TAKE_PROFIT_ORDER_TYPES
                and resting.side == exit_side
                and resting.stop_price == position.take_profit
            ):
                logger.warning(
                    "Adopting take-profit %s already resting for position %s",
                    resting.order_id,
                    position.id,
                )
                await self._linked_orders.save(resting, position.id)
                return
        await self._place_take_profit_order(
            position,
            position.take_profit,
            position.quantity,
        )
        logger.info(
            "Take-profit placed on retry for position %s",
            position.id,
            extra={"position_id": position.id, "symbol": position.symbol},
        )

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

        # Persist quantity and flag together right after the exchange fill, before
        # touching protective orders, so a later failure cannot re-trigger the exit.
        remaining = position.quantity - action.exit_quantity
        updated_position = position.model_copy(
            update={
                "quantity": remaining,
                "partial_exit_done": True,
                "updated_at": utc_now(),
            },
        )
        try:
            await self._state.update_position(updated_position)
        except Exception:
            logger.critical(
                "Partial exit executed on exchange for %s but failed to persist "
                "the reduced position; reconciliation required",
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

        await self._linked_orders.cancel_for_position(updated_position)
        if remaining > 0:
            await self._replace_protective_orders(updated_position)

    async def _replace_protective_orders(self, position: PositionSchema) -> None:
        # Each leg is attempted independently; a missing leg is left for reconciliation.
        placements = (
            ("stop-loss", self._place_stop_order, position.current_stop_loss),
            ("take-profit", self._place_take_profit_order, position.take_profit),
        )
        for name, place, price in placements:
            try:
                await place(position, price, position.quantity)
            except Exception:
                logger.critical(
                    "Failed to re-place %s after partial exit for %s; "
                    "position under-protected, reconciliation required",
                    name,
                    position.symbol,
                    extra={
                        "position_id": position.id,
                        "symbol": position.symbol,
                        "needs_reconciliation": True,
                    },
                    exc_info=True,
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
        await self._linked_orders.cancel_for_position(position)
        await self._state.remove_position(position.id)
        return order_response.effective_fill_price

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
        await self._linked_orders.save(response, position.id)

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
        await self._linked_orders.save(response, position.id)
