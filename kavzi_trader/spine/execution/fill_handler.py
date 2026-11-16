import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Literal

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.decision_message import DecisionMessageSchema
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.events.aggregate_type import AggregateType
from kavzi_trader.spine.execution.emergency_closer import EmergencyCloser
from kavzi_trader.spine.execution.event_recorder import ExecutionEventRecorder
from kavzi_trader.spine.execution.protective_orders import ProtectiveOrderPlacer
from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class FillHandler:
    """Turns a filled entry order into a persisted, protected position."""

    def __init__(
        self,
        state_manager: StateManager,
        placer: ProtectiveOrderPlacer,
        emergency_closer: EmergencyCloser,
        events: ExecutionEventRecorder,
        leverage_for: Callable[[str], int],
        liquidation_calculator: LiquidationCalculator | None,
    ) -> None:
        self._state = state_manager
        self._placer = placer
        self._emergency_closer = emergency_closer
        self._events = events
        self._leverage_for = leverage_for
        self._liquidation_calculator = liquidation_calculator

    async def on_order_filled(
        self,
        decision: DecisionMessageSchema,
        order: OrderResponseSchema,
    ) -> None:
        now = utc_now()
        leverage = self._leverage_for(decision.symbol)
        initial_margin = (
            (order.price * order.executed_qty) / Decimal(leverage)
            if leverage > 0
            else Decimal(0)
        )
        position_side: Literal["LONG", "SHORT"] = (
            "LONG" if decision.action == "LONG" else "SHORT"
        )
        liq_price = await self._estimate_liquidation(
            decision.symbol,
            position_side,
            order,
            leverage,
        )
        position = PositionSchema(
            id=decision.decision_id,
            symbol=decision.symbol,
            side=position_side,
            quantity=order.executed_qty,
            entry_price=order.price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            current_stop_loss=decision.stop_loss,
            management_config=decision.position_management,
            leverage=leverage,
            liquidation_price=liq_price,
            initial_margin=initial_margin,
            atr_at_entry=decision.current_atr if decision.current_atr > 0 else None,
            opened_at=now,
            updated_at=now,
        )
        try:
            await self._state.update_position(position)
        except Exception:
            logger.exception(
                "CRITICAL: Failed to persist filled position %s; "
                "triggering emergency close",
                position.id,
                extra={"position_id": position.id, "symbol": position.symbol},
            )
            await self._emergency_closer.close(position)
            return
        logger.info(
            "Position opened: id=%s %s %s qty=%s entry=%s SL=%s TP=%s",
            position.id,
            position.symbol,
            position.side,
            position.quantity,
            position.entry_price,
            position.stop_loss,
            position.take_profit,
            extra={
                "symbol": position.symbol,
                "position_id": position.id,
            },
        )
        # Effective risk = what the filled size actually risks to the stop.
        # Carried on the event (alongside decision_id) so outcome-attribution
        # can join decisions to fills and audit per-trade risk after the fact.
        effective_risk = order.executed_qty * abs(order.price - position.stop_loss)
        await self._events.record(
            aggregate_id=position.id,
            aggregate_type=AggregateType.POSITIONS,
            event_type="position_opened",
            data={
                "symbol": position.symbol,
                "side": position.side,
                "strategy": position.strategy,
                "decision_id": decision.decision_id,
                "entry_price": float(order.price),
                "stop_loss": float(position.stop_loss),
                "quantity": float(order.executed_qty),
                "effective_risk_usdt": float(effective_risk),
            },
        )
        if decision.action in {"LONG", "SHORT"}:
            try:
                await self._placer.place_initial(position)
            except Exception:
                logger.exception(
                    "CRITICAL: Unhandled error in protective order placement "
                    "for position %s; triggering emergency close",
                    position.id,
                    extra={"position_id": position.id, "symbol": position.symbol},
                )
                await self._emergency_closer.close(position)

    async def _estimate_liquidation(
        self,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        order: OrderResponseSchema,
        leverage: int,
    ) -> Decimal | None:
        if self._liquidation_calculator is None or leverage <= 0:
            return None
        try:
            return await self._liquidation_calculator.estimate_liquidation_price(
                symbol=symbol,
                side=side,
                entry_price=order.price,
                leverage=leverage,
                notional=order.price * order.executed_qty,
            )
        except Exception:
            logger.exception(
                "Failed to estimate liquidation price for %s; "
                "recording position with liquidation_price=None",
                symbol,
            )
            return None
