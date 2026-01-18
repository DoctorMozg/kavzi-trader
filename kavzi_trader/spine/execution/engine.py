import logging
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import (
    OrderResponseSchema,
    OrderSide,
    OrderStatus,
    OrderType,
)
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.execution.execution_result_schema import ExecutionResultSchema
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.schemas import OpenOrderSchema, PositionSchema

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Coordinates order execution from validated decision payloads."""

    def __init__(
        self,
        exchange: BinanceClient,
        state_manager: StateManager,
        risk_validator: DynamicRiskValidator,
        staleness_checker: StalenessChecker,
        translator: DecisionTranslator,
        monitor: OrderMonitor,
        event_store: RedisEventStore | None = None,
    ) -> None:
        self._exchange = exchange
        self._state_manager = state_manager
        self._risk_validator = risk_validator
        self._staleness_checker = staleness_checker
        self._translator = translator
        self._monitor = monitor
        self._event_store = event_store

    async def execute(self, decision: DecisionMessageSchema) -> ExecutionResultSchema:
        if self._staleness_checker.is_stale(
            decision.created_at_ms,
            decision.volatility_regime,
        ):
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="EXPIRED",
                executed_qty=0.0,
                executed_price=None,
                error_message="Decision expired",
            )

        if decision.action == "CLOSE":
            return await self._close_position(decision)

        side: Literal["LONG", "SHORT"] = "LONG" if decision.action == "BUY" else "SHORT"
        validation = await self._risk_validator.validate_trade(
            symbol=decision.symbol,
            side=side,
            entry_price=decision.entry_price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            current_atr=decision.current_atr,
            atr_history=decision.atr_history,
            state_manager=self._state_manager,
        )

        if not validation.is_valid:
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="REJECTED",
                executed_qty=0.0,
                executed_price=None,
                error_message="; ".join(validation.rejection_reasons),
            )

        return await self._execute_validated(decision, validation.recommended_size)

    async def _execute_validated(
        self,
        decision: DecisionMessageSchema,
        recommended_size: Decimal,
    ) -> ExecutionResultSchema:
        quantity_override = (
            recommended_size if recommended_size > 0 else decision.quantity
        )
        order_request = self._translator.translate(
            decision=decision,
            quantity_override=quantity_override,
        )

        try:
            await self._record_event(
                aggregate_id=decision.decision_id,
                aggregate_type="decision",
                event_type="order_created",
                data={"symbol": decision.symbol, "action": decision.action},
            )
            order_response = await self._exchange.create_order(
                symbol=order_request.symbol,
                side=order_request.side,
                order_type=order_request.order_type,
                quantity=order_request.quantity,
                price=order_request.price,
                time_in_force=order_request.time_in_force,
                client_order_id=order_request.client_order_id,
            )
        except Exception as exc:
            logger.exception("Failed to submit order for %s", decision.symbol)
            await self._record_event(
                aggregate_id=decision.decision_id,
                aggregate_type="decision",
                event_type="order_rejected",
                data={"symbol": decision.symbol, "reason": str(exc)},
            )
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="REJECTED",
                executed_qty=0.0,
                executed_price=None,
                error_message=str(exc),
            )

        await self._save_open_order(order_response)

        if order_response.status == OrderStatus.FILLED:
            await self._on_order_filled(decision, order_response)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=str(order_response.order_id),
                status="FILLED",
                executed_qty=float(order_response.executed_qty),
                executed_price=float(order_response.price),
                error_message=None,
            )

        monitored = await self._monitor.wait_for_completion(
            symbol=decision.symbol,
            order_id=order_response.order_id,
        )
        if monitored and monitored.status == OrderStatus.FILLED:
            await self._on_order_filled(decision, monitored)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=str(monitored.order_id),
                status="FILLED",
                executed_qty=float(monitored.executed_qty),
                executed_price=float(monitored.price),
                error_message=None,
            )

        return ExecutionResultSchema(
            decision_id=decision.decision_id,
            order_id=str(order_response.order_id),
            status="SUBMITTED",
            executed_qty=float(order_response.executed_qty),
            executed_price=float(order_response.price)
            if order_response.price is not None
            else None,
            error_message=None,
        )

    async def _close_position(
        self,
        decision: DecisionMessageSchema,
    ) -> ExecutionResultSchema:
        side = OrderSide.SELL if decision.action == "BUY" else OrderSide.BUY
        try:
            order_response = await self._exchange.create_order(
                symbol=decision.symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=decision.quantity,
            )
        except Exception as exc:
            logger.exception("Failed to close position for %s", decision.symbol)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="REJECTED",
                executed_qty=0.0,
                executed_price=None,
                error_message=str(exc),
            )

        return ExecutionResultSchema(
            decision_id=decision.decision_id,
            order_id=str(order_response.order_id),
            status="FILLED",
            executed_qty=float(order_response.executed_qty),
            executed_price=float(order_response.price),
            error_message=None,
        )

    async def _save_open_order(self, order: OrderResponseSchema) -> None:
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
            created_at=created_at,
        )
        await self._state_manager.save_order(open_order)

    async def _on_order_filled(
        self,
        decision: DecisionMessageSchema,
        order: OrderResponseSchema,
    ) -> None:
        now = utc_now()
        position = PositionSchema(
            id=decision.decision_id,
            symbol=decision.symbol,
            side=self._position_side(decision.action),
            quantity=order.executed_qty,
            entry_price=order.price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            current_stop_loss=decision.stop_loss,
            management_config=decision.position_management,
            opened_at=now,
            updated_at=now,
        )
        await self._state_manager.update_position(position)
        await self._record_event(
            aggregate_id=position.id,
            aggregate_type="position",
            event_type="position_opened",
            data={"symbol": position.symbol, "side": position.side},
        )
        if decision.action in {"BUY", "SELL"}:
            await self._place_protective_orders(position)

    async def _place_protective_orders(self, position: PositionSchema) -> None:
        stop_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        take_side = stop_side

        stop_price = self._stop_price_for_side(position.side, position.stop_loss)
        await self._exchange.create_order(
            symbol=position.symbol,
            side=stop_side,
            order_type=OrderType.STOP_LOSS_LIMIT,
            quantity=position.quantity,
            price=stop_price,
            stop_price=position.stop_loss,
        )

        await self._exchange.create_order(
            symbol=position.symbol,
            side=take_side,
            order_type=OrderType.TAKE_PROFIT_LIMIT,
            quantity=position.quantity,
            price=position.take_profit,
            stop_price=position.take_profit,
        )

    async def _record_event(
        self,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        data: dict[str, str | int | float | None],
    ) -> None:
        if self._event_store is None:
            return
        event = EventSchema(
            event_id=str(uuid4()),
            event_type=event_type,
            version=1,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            data=data,
            metadata={},
            timestamp=utc_now(),
        )
        await self._event_store.append(event)

    def _position_side(
        self,
        action: Literal["BUY", "SELL", "CLOSE"],
    ) -> Literal[
        "LONG",
        "SHORT",
    ]:
        return "LONG" if action == "BUY" else "SHORT"

    def _stop_price_for_side(self, side: str, stop_loss: Decimal) -> Decimal:
        adjustment = Decimal("0.999") if side == "LONG" else Decimal("1.001")
        return stop_loss * adjustment
