import logging

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.order_enums import OrderType
from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.events.aggregate_type import AggregateType
from kavzi_trader.spine.execution.emergency_closer import EmergencyCloser
from kavzi_trader.spine.execution.event_recorder import ExecutionEventRecorder
from kavzi_trader.spine.execution.linked_orders import LinkedOrderService
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class ProtectiveOrderPlacer:
    """Places the SL/TP bracket for a position and handles placement failures."""

    def __init__(
        self,
        exchange: ExchangeClient,
        state_manager: StateManager,
        linked_orders: LinkedOrderService,
        emergency_closer: EmergencyCloser,
        events: ExecutionEventRecorder,
    ) -> None:
        self._exchange = exchange
        self._state = state_manager
        self._linked_orders = linked_orders
        self._emergency_closer = emergency_closer
        self._events = events

    async def place_stop_loss(self, position: PositionSchema) -> None:
        stop_side = position.exit_side
        stop_response = await self._exchange.create_order(
            symbol=position.symbol,
            side=stop_side,
            order_type=OrderType.STOP_MARKET,
            quantity=position.quantity,
            stop_price=position.stop_loss,
            reduce_only=True,
        )
        await self._linked_orders.save(stop_response, position.id)
        logger.info(
            "Stop-loss placed for %s: stop_price=%s",
            position.symbol,
            position.stop_loss,
            extra={"symbol": position.symbol},
        )

    async def place_take_profit(self, position: PositionSchema) -> None:
        take_side = position.exit_side
        take_response = await self._exchange.create_order(
            symbol=position.symbol,
            side=take_side,
            order_type=OrderType.TAKE_PROFIT_MARKET,
            quantity=position.quantity,
            stop_price=position.take_profit,
            reduce_only=True,
        )
        await self._linked_orders.save(take_response, position.id)
        logger.info(
            "Take-profit placed for %s: stop_price=%s",
            position.symbol,
            position.take_profit,
            extra={"symbol": position.symbol},
        )

    async def place(
        self,
        position: PositionSchema,
        *,
        place_stop_loss: bool,
        place_take_profit: bool,
    ) -> None:
        """Place only the requested protective legs; never emergency-close.

        Reconciler-driven recovery path. If a leg fails the exception bubbles
        to `ReconciliationService._attempt_protective_recovery`, which records
        the failure as unrecoverable. The already-live leg is preserved; no
        duplicate orders are placed and no healthy position is auto-closed on
        exchange hiccups.
        """
        if place_stop_loss:
            await self.place_stop_loss(position)
        if place_take_profit:
            await self.place_take_profit(position)

    async def place_initial(self, position: PositionSchema) -> None:
        """Place SL+TP for a freshly filled position.

        Initial-fill semantics: SL failure escalates to emergency-close because
        the position has no live protection yet. Reconciler-driven retries MUST
        use `place` instead — that path keeps the live leg and
        classifies failures as unrecoverable rather than auto-closing.
        """
        try:
            await self.place_stop_loss(position)
        except Exception:
            logger.exception(
                "Failed to place stop-loss for position %s, closing position",
                position.id,
            )
            await self._emergency_closer.close(position)
            return

        try:
            await self.place_take_profit(position)
        except Exception:
            # Risk is bounded by the live SL — no emergency close. The flag lets
            # the position-management loop re-place the take-profit on a later tick.
            logger.exception(
                "Failed to place take-profit for position %s; stop-loss is active",
                position.id,
            )
            logger.warning(
                "Position %s is half-bracketed (SL only); TP retry scheduled",
                position.id,
                extra={
                    "needs_tp_retry": True,
                    "position_id": position.id,
                    "symbol": position.symbol,
                },
            )
            await self._flag_take_profit_retry(position)
            await self._events.record(
                aggregate_id=position.id,
                aggregate_type=AggregateType.POSITIONS,
                event_type="protective_order_failed",
                data={
                    "symbol": position.symbol,
                    "failed_order": "take_profit",
                    "stop_loss_active": True,
                },
            )
            await self._events.record(
                aggregate_id=position.id,
                aggregate_type=AggregateType.POSITIONS,
                event_type="position_half_bracketed",
                data={"symbol": position.symbol, "position_id": position.id},
            )

    async def _flag_take_profit_retry(self, position: PositionSchema) -> None:
        """Persist the half-bracket so the position loop re-places the TP."""
        flagged = position.model_copy(
            update={"needs_tp_retry": True, "updated_at": utc_now()},
        )
        try:
            await self._state.update_position(flagged)
        except Exception:
            logger.critical(
                "Failed to flag position %s for take-profit retry; "
                "it stays half-bracketed until reconciliation",
                position.id,
                extra={"position_id": position.id, "symbol": position.symbol},
                exc_info=True,
            )
