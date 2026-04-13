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
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.execution.execution_result_schema import ExecutionResultSchema
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.schemas import OpenOrderSchema, PositionSchema

_REGIME_SEVERITY = [
    VolatilityRegime.LOW,
    VolatilityRegime.NORMAL,
    VolatilityRegime.HIGH,
    VolatilityRegime.EXTREME,
]

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
        leverage: int = 3,
        report_populator: TradeReportPopulator | None = None,
        volatility_detector: VolatilityRegimeDetector | None = None,
        liquidation_calculator: LiquidationCalculator | None = None,
    ) -> None:
        self._exchange = exchange
        self._state_manager = state_manager
        self._risk_validator = risk_validator
        self._staleness_checker = staleness_checker
        self._translator = translator
        self._monitor = monitor
        self._event_store = event_store
        self._leverage = leverage
        self._report_populator = report_populator
        self._volatility_detector = volatility_detector
        self._liquidation_calculator = liquidation_calculator

    async def execute(self, decision: DecisionMessageSchema) -> ExecutionResultSchema:
        logger.info(
            "Executing decision %s for %s: action=%s",
            decision.decision_id,
            decision.symbol,
            decision.action,
            extra={
                "decision_id": decision.decision_id,
                "symbol": decision.symbol,
            },
        )
        staleness_regime = decision.volatility_regime
        if self._volatility_detector is not None:
            detected = self._volatility_detector.detect_regime(
                decision.current_atr,
                decision.atr_history,
            )
            if detected.regime != decision.volatility_regime:
                logger.info(
                    "Regime drift for %s: decision=%s detected=%s, using stricter",
                    decision.symbol,
                    decision.volatility_regime.value,
                    detected.regime.value,
                )
                staleness_regime = max(
                    decision.volatility_regime,
                    detected.regime,
                    key=lambda r: _REGIME_SEVERITY.index(r),
                )
        if self._staleness_checker.is_stale(
            decision.created_at_ms,
            staleness_regime,
        ):
            logger.info(
                "Decision %s EXPIRED for %s",
                decision.decision_id,
                decision.symbol,
                extra={"decision_id": decision.decision_id},
            )
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="EXPIRED",
                executed_qty=None,
                executed_price=None,
                error_message="Decision expired",
                needs_reconciliation=False,
            )

        if decision.action == "CLOSE":
            return await self._close_position(decision)

        side: Literal["LONG", "SHORT"] = decision.action  # type: ignore[assignment]
        validation = await self._risk_validator.validate_trade(
            symbol=decision.symbol,
            side=side,
            entry_price=decision.entry_price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            current_atr=decision.current_atr,
            atr_history=decision.atr_history,
            state_manager=self._state_manager,
            leverage=self._leverage,
            confidence=Decimal(str(decision.calibrated_confidence)),
            symbol_tier=decision.symbol_tier,
        )

        if not validation.is_valid:
            logger.info(
                "Decision %s REJECTED for %s: %s",
                decision.decision_id,
                decision.symbol,
                "; ".join(validation.rejection_reasons),
                extra={"decision_id": decision.decision_id},
            )
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="REJECTED",
                executed_qty=None,
                executed_price=None,
                error_message="; ".join(validation.rejection_reasons),
                needs_reconciliation=False,
            )

        return await self._execute_validated(decision, validation.recommended_size)

    async def _execute_validated(
        self,
        decision: DecisionMessageSchema,
        recommended_size: Decimal,
    ) -> ExecutionResultSchema:
        if recommended_size <= 0:
            # Risk validator said "pass" but returned zero size — a contradiction
            # that previously leaked into a zero-quantity order. Reject instead.
            logger.error(
                "Risk validator returned non-positive size %s for %s; rejecting",
                recommended_size,
                decision.symbol,
                extra={
                    "decision_id": decision.decision_id,
                    "symbol": decision.symbol,
                },
            )
            try:
                await self._record_event(
                    aggregate_id=decision.decision_id,
                    aggregate_type="decision",
                    event_type="order_rejected",
                    data={
                        "symbol": decision.symbol,
                        "reason": "risk_validator_returned_zero_size",
                    },
                )
            except Exception:
                logger.exception(
                    "Failed to record order_rejected event for %s",
                    decision.decision_id,
                )
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="REJECTED",
                executed_qty=None,
                executed_price=None,
                error_message="risk_validator_returned_zero_size",
                needs_reconciliation=False,
            )
        order_request = self._translator.translate(
            decision=decision,
            quantity_override=recommended_size,
        )
        logger.debug(
            "Order translated: symbol=%s side=%s qty=%s price=%s",
            order_request.symbol,
            order_request.side,
            order_request.quantity,
            order_request.price,
        )

        try:
            await self._record_event(
                aggregate_id=decision.decision_id,
                aggregate_type="decision",
                event_type="order_created",
                data={"symbol": decision.symbol, "action": decision.action},
            )
        except Exception:
            logger.exception(
                "Failed to record order_created event for %s",
                decision.decision_id,
            )
        try:
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
            try:
                await self._record_event(
                    aggregate_id=decision.decision_id,
                    aggregate_type="decision",
                    event_type="order_rejected",
                    data={"symbol": decision.symbol, "reason": str(exc)},
                )
            except Exception:
                logger.exception(
                    "Failed to record order_rejected event for %s",
                    decision.decision_id,
                )
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="REJECTED",
                executed_qty=None,
                executed_price=None,
                error_message=str(exc),
                needs_reconciliation=False,
            )

        try:
            await self._save_open_order(order_response)
        except Exception:
            logger.exception(
                "Failed to save open order for %s, order placed but not tracked",
                decision.symbol,
                extra={"decision_id": decision.decision_id},
            )
        logger.info(
            "Order submitted for %s: order_id=%s status=%s",
            decision.symbol,
            order_response.order_id,
            order_response.status.value,
            extra={
                "decision_id": decision.decision_id,
                "symbol": decision.symbol,
            },
        )

        if order_response.status == OrderStatus.FILLED:
            await self._on_order_filled(decision, order_response)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=str(order_response.order_id),
                status="FILLED",
                executed_qty=order_response.executed_qty,
                executed_price=order_response.price,
                error_message=None,
                needs_reconciliation=False,
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
                executed_qty=monitored.executed_qty,
                executed_price=monitored.price,
                error_message=None,
                needs_reconciliation=False,
            )

        return ExecutionResultSchema(
            decision_id=decision.decision_id,
            order_id=str(order_response.order_id),
            status="SUBMITTED",
            executed_qty=order_response.executed_qty,
            executed_price=order_response.price,
            error_message=None,
            needs_reconciliation=True,
        )

    async def _close_position(
        self,
        decision: DecisionMessageSchema,
    ) -> ExecutionResultSchema:
        logger.info(
            "Closing position for %s, decision_id=%s",
            decision.symbol,
            decision.decision_id,
            extra={"symbol": decision.symbol},
        )
        position = await self._state_manager.get_position(decision.symbol)
        if position is None:
            logger.error("No open position found for %s", decision.symbol)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="REJECTED",
                executed_qty=None,
                executed_price=None,
                error_message=f"No open position for {decision.symbol}",
                needs_reconciliation=False,
            )
        side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        try:
            order_response = await self._exchange.create_order(
                symbol=decision.symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=position.quantity,
                reduce_only=True,
            )
        except Exception as exc:
            logger.exception("Failed to close position for %s", decision.symbol)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="REJECTED",
                executed_qty=None,
                executed_price=None,
                error_message=str(exc),
                needs_reconciliation=False,
            )

        # Close submitted successfully — tear down local state. Each step is
        # isolated so a Redis failure cannot mask the on-exchange close.
        try:
            await self._cancel_linked_orders(position)
        except Exception:
            logger.exception(
                "Failed to cancel linked orders for closed position %s",
                position.id,
            )
        try:
            await self._state_manager.remove_position(position.id)
        except Exception:
            logger.exception(
                "Failed to remove position %s from state after close",
                position.id,
            )
        try:
            await self._record_event(
                aggregate_id=position.id,
                aggregate_type="position",
                event_type="position_closed",
                data={"symbol": position.symbol, "reason": "close_action"},
            )
        except Exception:
            logger.exception(
                "Failed to record position_closed event for %s",
                position.id,
            )

        return ExecutionResultSchema(
            decision_id=decision.decision_id,
            order_id=str(order_response.order_id),
            status="FILLED",
            executed_qty=order_response.executed_qty,
            executed_price=self._effective_fill_price(order_response),
            error_message=None,
            needs_reconciliation=False,
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
        leverage = self._leverage
        initial_margin = (
            (order.price * order.executed_qty) / Decimal(leverage)
            if leverage > 0
            else Decimal(0)
        )
        position_side = self._position_side(decision.action)
        liq_price: Decimal | None = None
        if self._liquidation_calculator is not None and leverage > 0:
            try:
                liq_price = (
                    await self._liquidation_calculator.estimate_liquidation_price(
                        symbol=decision.symbol,
                        side=position_side,
                        entry_price=order.price,
                        leverage=leverage,
                        notional=order.price * order.executed_qty,
                    )
                )
            except Exception:
                logger.exception(
                    "Failed to estimate liquidation price for %s; "
                    "recording position with liquidation_price=None",
                    decision.symbol,
                )
                liq_price = None
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
            opened_at=now,
            updated_at=now,
        )
        try:
            await self._state_manager.update_position(position)
        except Exception:
            logger.exception(
                "CRITICAL: Failed to persist filled position %s; "
                "triggering emergency close",
                position.id,
                extra={"position_id": position.id, "symbol": position.symbol},
            )
            await self._emergency_close(position)
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
        try:
            await self._record_event(
                aggregate_id=position.id,
                aggregate_type="position",
                event_type="position_opened",
                data={"symbol": position.symbol, "side": position.side},
            )
        except Exception:
            logger.exception(
                "Failed to record position_opened event for %s",
                position.id,
            )
        if decision.action in {"LONG", "SHORT"}:
            try:
                await self._place_protective_orders(position)
            except Exception:
                logger.exception(
                    "CRITICAL: Unhandled error in protective order placement "
                    "for position %s; triggering emergency close",
                    position.id,
                    extra={"position_id": position.id, "symbol": position.symbol},
                )
                await self._emergency_close(position)

    async def _place_stop_loss(self, position: PositionSchema) -> None:
        stop_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        stop_response = await self._exchange.create_order(
            symbol=position.symbol,
            side=stop_side,
            order_type=OrderType.STOP_MARKET,
            quantity=position.quantity,
            stop_price=position.stop_loss,
            reduce_only=True,
        )
        await self._save_linked_order(stop_response, position.id)
        logger.info(
            "Stop-loss placed for %s: stop_price=%s",
            position.symbol,
            position.stop_loss,
            extra={"symbol": position.symbol},
        )

    async def _place_take_profit(self, position: PositionSchema) -> None:
        take_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        take_response = await self._exchange.create_order(
            symbol=position.symbol,
            side=take_side,
            order_type=OrderType.TAKE_PROFIT_MARKET,
            quantity=position.quantity,
            stop_price=position.take_profit,
            reduce_only=True,
        )
        await self._save_linked_order(take_response, position.id)
        logger.info(
            "Take-profit placed for %s: stop_price=%s",
            position.symbol,
            position.take_profit,
            extra={"symbol": position.symbol},
        )

    async def _place_protective_subset(
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
            await self._place_stop_loss(position)
        if place_take_profit:
            await self._place_take_profit(position)

    async def _place_protective_orders(self, position: PositionSchema) -> None:
        """Place SL+TP for a freshly filled position.

        Initial-fill semantics: SL failure escalates to emergency-close because
        the position has no live protection yet. Reconciler-driven retries MUST
        use `_place_protective_subset` instead — that path keeps the live leg
        and classifies failures as unrecoverable rather than auto-closing.
        """
        try:
            await self._place_stop_loss(position)
        except Exception:
            logger.exception(
                "Failed to place stop-loss for position %s, closing position",
                position.id,
            )
            await self._emergency_close(position)
            return

        try:
            await self._place_take_profit(position)
        except Exception:
            # Risk is bounded by the live SL — no emergency close. We surface
            # the broken-bracket state so the position-management loop (which
            # treats positions without a linked TP order as needing retry)
            # can re-place the take-profit on the next tick.
            logger.exception(
                "Failed to place take-profit for position %s; stop-loss is active",
                position.id,
            )
            logger.warning(
                "Position %s is half-bracketed (SL only); TP retry required",
                position.id,
                extra={
                    "needs_tp_retry": True,
                    "position_id": position.id,
                    "symbol": position.symbol,
                },
            )
            try:
                await self._record_event(
                    aggregate_id=position.id,
                    aggregate_type="position",
                    event_type="protective_order_failed",
                    data={
                        "symbol": position.symbol,
                        "failed_order": "take_profit",
                        "stop_loss_active": True,
                    },
                )
            except Exception:
                logger.exception(
                    "Failed to record protective_order_failed event for %s",
                    position.id,
                )
            try:
                await self._record_event(
                    aggregate_id=position.id,
                    aggregate_type="position",
                    event_type="position_half_bracketed",
                    data={
                        "symbol": position.symbol,
                        "position_id": position.id,
                    },
                )
            except Exception:
                logger.exception(
                    "Failed to record position_half_bracketed event for %s",
                    position.id,
                )

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
        await self._state_manager.save_order(open_order)

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

    def _effective_fill_price(
        self,
        order: OrderResponseSchema,
    ) -> Decimal | None:
        """Return the weighted-average fill price, or None when unknown.

        Binance futures MARKET orders return `price=0` in the REST response;
        the real fill price must be reconstructed from the `fills` array.
        """
        fills = order.fills
        if not fills:
            return order.price if order.price > 0 else None
        total_qty = sum((f.qty for f in fills), Decimal(0))
        if total_qty <= 0:
            return order.price if order.price > 0 else None
        weighted = sum((f.price * f.qty for f in fills), Decimal(0))
        return weighted / total_qty

    async def _cancel_linked_orders(self, position: PositionSchema) -> None:
        linked = await self._state_manager.orders.get_by_position(position.id)
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
            try:
                await self._state_manager.remove_order(order.order_id)
            except Exception:
                logger.exception(
                    "Failed to remove linked order %s from state for position %s",
                    order.order_id,
                    position.id,
                )

    async def _emergency_close(self, position: PositionSchema) -> None:
        """Close position on exchange when protective orders cannot be placed."""
        close_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        exit_price: Decimal | None = None
        try:
            order_response = await self._exchange.create_order(
                symbol=position.symbol,
                side=close_side,
                order_type=OrderType.MARKET,
                quantity=position.quantity,
                reduce_only=True,
            )
            exit_price = self._effective_fill_price(order_response)
            await self._state_manager.remove_position(position.id)
            logger.warning(
                "Emergency-closed position %s for %s",
                position.id,
                position.symbol,
            )
        except Exception:
            logger.exception(
                "CRITICAL: Emergency close FAILED for position %s — "
                "manual intervention required",
                position.id,
            )
        try:
            await self._record_event(
                aggregate_id=position.id,
                aggregate_type="position",
                event_type="emergency_close",
                data={"symbol": position.symbol, "reason": "protective_order_failure"},
            )
        except Exception:
            logger.exception(
                "Failed to record emergency_close event for %s",
                position.id,
            )
        if exit_price is not None and self._report_populator is not None:
            try:
                side: Literal["LONG", "SHORT"] = position.side  # type: ignore[assignment]
                await self._report_populator.record_position_close(
                    symbol=position.symbol,
                    side=side,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    close_reason="Emergency close",
                    leverage=position.leverage,
                    opened_at=position.opened_at,
                )
            except Exception:
                logger.exception(
                    "Failed to report emergency close for %s",
                    position.symbol,
                )

    def _position_side(
        self,
        action: Literal["LONG", "SHORT", "CLOSE"],
    ) -> Literal[
        "LONG",
        "SHORT",
    ]:
        return "LONG" if action == "LONG" else "SHORT"
