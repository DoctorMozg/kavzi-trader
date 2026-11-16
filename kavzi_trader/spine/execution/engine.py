import logging
from decimal import Decimal

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.commons.clock import Clock
from kavzi_trader.commons.system_clock import SYSTEM_CLOCK
from kavzi_trader.domain.decision_message import DecisionMessageSchema
from kavzi_trader.domain.execution_result import ExecutionResultSchema
from kavzi_trader.domain.order_enums import OrderStatus, OrderType
from kavzi_trader.events.aggregate_type import AggregateType
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.spine.execution.close_recorder import PositionCloseRecorder
from kavzi_trader.spine.execution.decision_validator import DecisionValidator
from kavzi_trader.spine.execution.emergency_closer import EmergencyCloser
from kavzi_trader.spine.execution.event_recorder import ExecutionEventRecorder
from kavzi_trader.spine.execution.fill_handler import FillHandler
from kavzi_trader.spine.execution.linked_orders import LinkedOrderService
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.pending_entries import PendingEntryManager
from kavzi_trader.spine.execution.protective_orders import ProtectiveOrderPlacer
from kavzi_trader.spine.execution.rebalance_executor import RebalanceExecutor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.execution.unfilled_entry import UnfilledEntryResolver
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Coordinates order execution from validated decision payloads."""

    def __init__(
        self,
        exchange: ExchangeClient,
        state_manager: StateManager,
        risk_validator: DynamicRiskValidator,
        staleness_checker: StalenessChecker,
        translator: DecisionTranslator,
        monitor: OrderMonitor,
        event_store: RedisEventStore | None = None,
        leverage: int = 3,
        close_recorder: PositionCloseRecorder | None = None,
        volatility_detector: VolatilityRegimeDetector | None = None,
        liquidation_calculator: LiquidationCalculator | None = None,
        pullback_entry_expiry_ms: int = 1_800_000,
        symbol_leverage: dict[str, int] | None = None,
        precision: SymbolPrecision | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._exchange = exchange
        self._state_manager = state_manager
        self._translator = translator
        self._monitor = monitor
        self._leverage = leverage
        self._symbol_leverage = symbol_leverage or {}

        self._validator = DecisionValidator(
            risk_validator,
            staleness_checker,
            state_manager,
            self._leverage_for,
            volatility_detector,
        )
        self._events = ExecutionEventRecorder(event_store, clock)
        self._linked_orders = LinkedOrderService(exchange, state_manager, clock)
        self._emergency_closer = EmergencyCloser(
            exchange,
            state_manager,
            self._events,
            close_recorder,
        )
        self._placer = ProtectiveOrderPlacer(
            exchange,
            state_manager,
            self._linked_orders,
            self._emergency_closer,
            self._events,
            clock,
        )
        self._fill_handler = FillHandler(
            state_manager,
            self._placer,
            self._emergency_closer,
            self._events,
            self._leverage_for,
            liquidation_calculator,
            clock,
        )
        self._pending_entries = PendingEntryManager(
            exchange,
            state_manager,
            self._fill_handler,
            pullback_entry_expiry_ms,
        )
        self._unfilled_entries = UnfilledEntryResolver(
            exchange,
            state_manager,
            self._fill_handler,
            self._pending_entries,
        )
        self._rebalance = RebalanceExecutor(
            exchange=exchange,
            state_manager=state_manager,
            risk_validator=risk_validator,
            placer=self._placer,
            linked_orders=self._linked_orders,
            emergency_closer=self._emergency_closer,
            events=self._events,
            monitor=monitor,
            leverage_for=self._leverage_for,
            close_recorder=close_recorder,
            precision=precision,
            clock=clock,
        )

    @property
    def rebalance(self) -> RebalanceExecutor:
        """Executor for target-weight intents; the bracket path never uses it."""
        return self._rebalance

    @property
    def protective_orders(self) -> ProtectiveOrderPlacer:
        """Placer the reconciler uses to restore missing SL/TP legs."""
        return self._placer

    def _leverage_for(self, symbol: str) -> int:
        # Mirrors the leverage trade.py sets on the exchange for each symbol.
        return self._symbol_leverage.get(symbol, self._leverage)

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

        regime_outcome = self._validator.validate_regime_drift(decision)
        effective_regime = regime_outcome.effective_regime or decision.volatility_regime

        staleness_outcome = self._validator.validate_staleness(
            decision, effective_regime
        )
        if not staleness_outcome.passed:
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
                error_message=staleness_outcome.reason,
                needs_reconciliation=False,
            )

        if decision.action == "CLOSE":
            return await self._close_position(decision)

        risk_outcome, risk_result = await self._validator.validate_risk(decision)
        if not risk_outcome.passed:
            logger.info(
                "Decision %s REJECTED for %s: %s",
                decision.decision_id,
                decision.symbol,
                risk_outcome.reason,
                extra={"decision_id": decision.decision_id},
            )
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=None,
                status="REJECTED",
                executed_qty=None,
                executed_price=None,
                error_message=risk_outcome.reason,
                needs_reconciliation=False,
            )

        return await self._execute_validated(decision, risk_result.recommended_size)

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
            await self._record_rejection(
                decision,
                "risk_validator_returned_zero_size",
            )
            return self._rejected(decision, "risk_validator_returned_zero_size")
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

        await self._events.record(
            aggregate_id=decision.decision_id,
            aggregate_type=AggregateType.DECISIONS,
            event_type="order_created",
            data={"symbol": decision.symbol, "action": decision.action},
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
            # Preserve the full exception text on the return path; truncate
            # only in the log preview so downstream consumers (reconciler,
            # dashboards) see the complete reason.
            error_text = str(exc)
            logger.exception(
                "Failed to submit order for %s",
                decision.symbol,
                extra={"error_message_preview": error_text[:200]},
            )
            await self._record_rejection(decision, error_text)
            return self._rejected(decision, error_text)

        try:
            await self._linked_orders.save(order_response)
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
            await self._fill_handler.on_order_filled(decision, order_response)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=str(order_response.order_id),
                status="FILLED",
                executed_qty=order_response.executed_qty,
                executed_price=order_response.effective_fill_price,
                error_message=None,
                needs_reconciliation=False,
            )

        if decision.entry_tactic == "PULLBACK_TO_LEVEL":
            # A pullback limit rests away from price; do NOT block the
            # execution loop waiting on it. Register it for the async
            # pending-entry sweep, which protects it on fill and cancels it
            # on candle expiry.
            await self._pending_entries.register(decision, order_response)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=str(order_response.order_id),
                status="SUBMITTED",
                executed_qty=order_response.executed_qty,
                executed_price=None,
                error_message=None,
                needs_reconciliation=True,
            )

        monitored = await self._monitor.wait_for_completion(
            symbol=decision.symbol,
            order_id=order_response.order_id,
        )
        if monitored and monitored.status == OrderStatus.FILLED:
            await self._fill_handler.on_order_filled(decision, monitored)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=str(monitored.order_id),
                status="FILLED",
                executed_qty=monitored.executed_qty,
                executed_price=monitored.effective_fill_price,
                error_message=None,
                needs_reconciliation=False,
            )

        return await self._unfilled_entries.resolve(
            decision,
            order_response,
            monitored,
        )

    async def process_pending_entries(self, now_ms: int) -> None:
        """Sweep resting pullback entries: protect on fill, cancel on expiry.

        Invoked periodically by the execution loop.
        """
        await self._pending_entries.sweep(now_ms)

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
            return self._rejected(decision, f"No open position for {decision.symbol}")
        side = position.exit_side
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
            return self._rejected(decision, str(exc))

        # Close submitted successfully — tear down local state. Each step is
        # isolated so a Redis failure cannot mask the on-exchange close.
        try:
            await self._linked_orders.cancel_for_position(position)
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
        await self._events.record(
            aggregate_id=position.id,
            aggregate_type=AggregateType.POSITIONS,
            event_type="position_closed",
            data={
                "symbol": position.symbol,
                "reason": "close_action",
                "strategy": position.strategy,
            },
        )

        return ExecutionResultSchema(
            decision_id=decision.decision_id,
            order_id=str(order_response.order_id),
            status="FILLED",
            executed_qty=order_response.executed_qty,
            executed_price=order_response.effective_fill_price,
            error_message=None,
            needs_reconciliation=False,
        )

    async def _record_rejection(
        self,
        decision: DecisionMessageSchema,
        reason: str,
    ) -> None:
        await self._events.record(
            aggregate_id=decision.decision_id,
            aggregate_type=AggregateType.DECISIONS,
            event_type="order_rejected",
            data={"symbol": decision.symbol, "reason": reason},
        )

    def _rejected(
        self,
        decision: DecisionMessageSchema,
        reason: str,
    ) -> ExecutionResultSchema:
        return ExecutionResultSchema(
            decision_id=decision.decision_id,
            order_id=None,
            status="REJECTED",
            executed_qty=None,
            executed_price=None,
            error_message=reason,
            needs_reconciliation=False,
        )
