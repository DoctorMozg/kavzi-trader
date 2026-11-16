import logging
from collections.abc import Callable
from decimal import ROUND_DOWN, Decimal

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.commons.clock import Clock
from kavzi_trader.commons.system_clock import SYSTEM_CLOCK
from kavzi_trader.domain.execution_result import ExecutionResultSchema
from kavzi_trader.domain.order_enums import OrderSide, OrderStatus, OrderType
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.domain.state_schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)
from kavzi_trader.events.aggregate_type import AggregateType
from kavzi_trader.spine.execution.close_recorder import PositionCloseRecorder
from kavzi_trader.spine.execution.emergency_closer import EmergencyCloser
from kavzi_trader.spine.execution.event_recorder import ExecutionEventRecorder
from kavzi_trader.spine.execution.linked_orders import LinkedOrderService
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.protective_orders import ProtectiveOrderPlacer
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from kavzi_trader.spine.risk.rebalance_validation_params_schema import (
    RebalanceValidationParamsSchema,
)
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)

logger = logging.getLogger(__name__)

# Same truncation the position sizer applies, so a target never rounds up.
_QUANTITY_QUANT = Decimal("0.00000001")
_REMEMBERED_INTENTS = 1024


class RebalanceExecutor:
    """Moves one symbol's long position to a target weight of equity."""

    def __init__(
        self,
        *,
        exchange: ExchangeClient,
        state_manager: StateManager,
        risk_validator: DynamicRiskValidator,
        placer: ProtectiveOrderPlacer,
        linked_orders: LinkedOrderService,
        emergency_closer: EmergencyCloser,
        events: ExecutionEventRecorder,
        monitor: OrderMonitor,
        leverage_for: Callable[[str], int],
        close_recorder: PositionCloseRecorder | None,
        precision: SymbolPrecision | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._precision = precision
        self._clock = clock
        self._exchange = exchange
        self._state = state_manager
        self._risk = risk_validator
        self._placer = placer
        self._linked_orders = linked_orders
        self._emergency_closer = emergency_closer
        self._events = events
        self._monitor = monitor
        self._leverage_for = leverage_for
        self._close_recorder = close_recorder
        # Queue redelivery guard; the absolute target already makes a replay a no-op.
        self._done: dict[str, None] = {}

    async def execute(self, intent: TargetWeightIntentSchema) -> ExecutionResultSchema:
        if intent.intent_id in self._done:
            return self._no_order(intent, "duplicate_intent")
        account = await self._state.get_account_state()
        if account is None:
            return await self._reject(intent, "account_state_unavailable")
        position = await self._state.get_position(intent.symbol)
        if position is not None and (
            position.exit_policy != "SIGNAL" or position.strategy != intent.strategy
        ):
            holder = f"{position.strategy}/{position.exit_policy}"
            return await self._reject(intent, f"{intent.symbol} is held by {holder}")

        price = await self._state.get_current_price(intent.symbol)
        equity = account.total_balance_usdt + account.unrealized_pnl
        current_qty = position.quantity if position is not None else Decimal(0)
        target_qty = self._floor_qty(
            intent.symbol,
            intent.target_weight * equity / price,
        )
        delta = target_qty - current_qty
        # A full close is reduce-only, which the exchange lets under min notional.
        too_small = target_qty > 0 and abs(delta) * price < (
            self._risk.min_position_notional_usd
        )
        skip_reason = (
            "within_tolerance"
            if delta == 0 or too_small
            else self._untradable_reason(intent.symbol, delta, price)
        )
        if skip_reason is not None:
            self._remember(intent)
            return self._no_order(intent, skip_reason)

        stop_price = price * (1 - intent.disaster_stop_pct)
        reasons = await self._risk.validate_rebalance(
            RebalanceValidationParamsSchema(
                symbol=intent.symbol,
                mark_price=price,
                current_qty=current_qty,
                target_qty=target_qty,
                equity=equity,
                leverage=self._leverage_for(intent.symbol),
                disaster_stop_price=stop_price,
                expires_at_ms=intent.expires_at_ms,
                now_ms=self._clock.now_ms(),
            ),
            self._state,
        )
        if reasons:
            return await self._reject(intent, "; ".join(reasons))

        await self._events.record(
            aggregate_id=intent.intent_id,
            aggregate_type=AggregateType.DECISIONS,
            event_type="order_created",
            data={
                "symbol": intent.symbol,
                "action": "BUY" if delta > 0 else "SELL",
                "strategy": intent.strategy,
            },
        )
        if position is not None and target_qty == 0:
            result = await self._close(intent, position, price)
        else:
            result = await self._resize(intent, position, delta, price)
        if result.status == "FILLED":
            self._remember(intent)
        return result

    async def _resize(
        self,
        intent: TargetWeightIntentSchema,
        position: PositionSchema | None,
        delta: Decimal,
        price: Decimal,
    ) -> ExecutionResultSchema:
        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        order = await self._market_order(intent.symbol, side, abs(delta), delta < 0)
        if order is None:
            return await self._reject(intent, "market_order_not_filled")
        fill_qty = order.executed_qty
        fill_price = order.effective_fill_price or price

        updated = self._apply_fill(intent, position, side, fill_qty, fill_price)
        try:
            await self._state.update_position(updated)
        except Exception:
            logger.exception(
                "CRITICAL: Failed to persist rebalanced position %s; "
                "triggering emergency close",
                updated.id,
                extra={"position_id": updated.id, "symbol": updated.symbol},
            )
            await self._emergency_closer.close(updated)
            return await self._reject(intent, "position_persist_failed")

        # Cancel-then-place leaves a short unprotected window; the old stop
        # has the wrong quantity and Binance may refuse overlapping reduce-only stops.
        if position is not None:
            await self._linked_orders.cancel_for_position(position)
        await self._placer.place_initial(updated)

        event_type = "position_opened" if position is None else "position_resized"
        await self._events.record(
            aggregate_id=updated.id,
            aggregate_type=AggregateType.POSITIONS,
            event_type=event_type,
            data={
                "symbol": updated.symbol,
                "side": updated.side,
                "strategy": updated.strategy,
                "decision_id": intent.intent_id,
                "entry_price": float(updated.entry_price),
                "stop_loss": float(updated.stop_loss),
                "quantity": float(updated.quantity),
            },
        )
        logger.info(
            "Position %s %s: id=%s qty=%s entry=%s SL=%s",
            event_type,
            updated.symbol,
            updated.id,
            updated.quantity,
            updated.entry_price,
            updated.stop_loss,
            extra={"symbol": updated.symbol, "position_id": updated.id},
        )
        return self._filled(intent, order, fill_qty, fill_price)

    def _apply_fill(
        self,
        intent: TargetWeightIntentSchema,
        position: PositionSchema | None,
        side: OrderSide,
        fill_qty: Decimal,
        fill_price: Decimal,
    ) -> PositionSchema:
        now = self._clock.now()
        leverage = self._leverage_for(intent.symbol)
        if position is None:
            quantity, entry = fill_qty, fill_price
        elif side == OrderSide.BUY:
            quantity = position.quantity + fill_qty
            entry = (
                position.entry_price * position.quantity + fill_price * fill_qty
            ) / quantity
        else:
            quantity, entry = position.quantity - fill_qty, position.entry_price
        stop = self._round_stop(intent.symbol, entry * (1 - intent.disaster_stop_pct))
        if position is None:
            return PositionSchema(
                id=intent.intent_id,
                symbol=intent.symbol,
                side="LONG",
                quantity=quantity,
                entry_price=entry,
                stop_loss=stop,
                take_profit=None,
                current_stop_loss=stop,
                management_config=PositionManagementConfigSchema(),
                strategy=intent.strategy,
                exit_policy="SIGNAL",
                leverage=leverage,
                initial_margin=entry * quantity / Decimal(leverage),
                opened_at=now,
                updated_at=now,
            )
        return position.model_copy(
            update={
                "quantity": quantity,
                "entry_price": entry,
                "stop_loss": stop,
                "current_stop_loss": stop,
                "initial_margin": entry * quantity / Decimal(leverage),
                "updated_at": now,
            },
        )

    def _floor_qty(self, symbol: str, qty: Decimal) -> Decimal:
        if self._precision is None:
            return qty.quantize(_QUANTITY_QUANT, rounding=ROUND_DOWN)
        return self._precision.round_qty(symbol, qty, market=True)

    def _round_stop(self, symbol: str, stop: Decimal) -> Decimal:
        if self._precision is None:
            return stop
        return self._precision.round_stop_loss(symbol, stop, is_long=True)

    def _untradable_reason(
        self,
        symbol: str,
        delta: Decimal,
        price: Decimal,
    ) -> str | None:
        """Why the exchange would refuse this resize, e.g. under minQty."""
        if self._precision is None:
            return None
        reason = self._precision.check_qty(
            symbol,
            abs(delta),
            price,
            market=True,
            reduce_only=delta < 0,
        )
        return None if reason is None else f"order_not_tradable: {reason}"

    async def _close(
        self,
        intent: TargetWeightIntentSchema,
        position: PositionSchema,
        price: Decimal,
    ) -> ExecutionResultSchema:
        order = await self._market_order(
            position.symbol,
            position.exit_side,
            position.quantity,
            reduce_only=True,
        )
        if order is None:
            return await self._reject(intent, "market_order_not_filled")
        exit_price = order.effective_fill_price or price

        # The exchange close already happened; isolate each local teardown step.
        try:
            await self._linked_orders.cancel_for_position(position)
            await self._state.remove_position(position.id)
        except Exception:
            logger.exception(
                "Failed to tear down closed position %s",
                position.id,
                extra={"position_id": position.id, "symbol": position.symbol},
            )
        await self._events.record(
            aggregate_id=position.id,
            aggregate_type=AggregateType.POSITIONS,
            event_type="position_closed",
            data={
                "symbol": position.symbol,
                "reason": "strategy_signal",
                "strategy": position.strategy,
            },
        )
        if self._close_recorder is not None:
            try:
                await self._close_recorder.record_position_close(
                    position,
                    "Strategy signal",
                    exit_price,
                )
            except Exception:
                logger.exception(
                    "Failed to report close for %s",
                    position.symbol,
                    extra={"position_id": position.id},
                )
        return self._filled(intent, order, order.executed_qty, exit_price)

    async def _market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        reduce_only: bool,
    ) -> OrderResponseSchema | None:
        order = await self._exchange.create_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            reduce_only=reduce_only,
        )
        if order.status != OrderStatus.FILLED:
            monitored = await self._monitor.wait_for_completion(symbol, order.order_id)
            if monitored is None or monitored.status != OrderStatus.FILLED:
                logger.error(
                    "Rebalance market order %s for %s not filled; reconcile",
                    order.order_id,
                    symbol,
                )
                return None
            order = monitored
        return order

    def _remember(self, intent: TargetWeightIntentSchema) -> None:
        self._done[intent.intent_id] = None
        if len(self._done) > _REMEMBERED_INTENTS:
            self._done.pop(next(iter(self._done)))

    @staticmethod
    def _filled(
        intent: TargetWeightIntentSchema,
        order: OrderResponseSchema,
        quantity: Decimal,
        price: Decimal,
    ) -> ExecutionResultSchema:
        return ExecutionResultSchema(
            decision_id=intent.intent_id,
            order_id=str(order.order_id),
            status="FILLED",
            executed_qty=quantity,
            executed_price=price,
            error_message=None,
            needs_reconciliation=False,
        )

    @staticmethod
    def _no_order(
        intent: TargetWeightIntentSchema,
        reason: str,
    ) -> ExecutionResultSchema:
        return ExecutionResultSchema(
            decision_id=intent.intent_id,
            order_id=None,
            status="REJECTED",
            executed_qty=None,
            executed_price=None,
            error_message=reason,
            needs_reconciliation=False,
        )

    async def _reject(
        self,
        intent: TargetWeightIntentSchema,
        reason: str,
    ) -> ExecutionResultSchema:
        logger.info(
            "Target-weight intent %s rejected for %s: %s",
            intent.intent_id,
            intent.symbol,
            reason,
            extra={"intent_id": intent.intent_id, "symbol": intent.symbol},
        )
        await self._events.record(
            aggregate_id=intent.intent_id,
            aggregate_type=AggregateType.DECISIONS,
            event_type="order_rejected",
            data={
                "symbol": intent.symbol,
                "reason": reason,
                "strategy": intent.strategy,
            },
        )
        return self._no_order(intent, reason)
