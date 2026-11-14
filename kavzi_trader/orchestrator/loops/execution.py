from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Literal, cast

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.execution_result_schema import ExecutionResultSchema
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)

# How often the loop sweeps resting PULLBACK entry limits for fill/expiry.
# Decoupled from decision consumption so a quiet queue still ages out
# unfilled pullback entries promptly.
_PENDING_SWEEP_INTERVAL_MS = 5_000

_PROCESSING_KEY = "kt:decisions:processing"
_FAILED_KEY = "kt:decisions:failed"
_MAX_DECISION_ATTEMPTS = 3


class ExecutionLoop:
    """Consumes queued decisions and executes orders."""

    def __init__(
        self,
        redis_client: RedisStateClient,
        engine: ExecutionEngine,
        state_manager: StateManager,
        queue_key: str = "kt:decisions:pending",
        report_populator: TradeReportPopulator | None = None,
    ) -> None:
        self._redis_client = redis_client
        self._engine = engine
        self._state_manager = state_manager
        self._queue_key = queue_key
        self._report_populator = report_populator
        self._last_pending_sweep_ms = 0
        self._attempts: dict[str, int] = {}

    async def run(self) -> None:
        logger.info(
            "ExecutionLoop started, listening on queue %s",
            self._queue_key,
        )
        await self._recover_in_flight()
        while True:
            try:
                await self._maybe_sweep_pending_entries()
                # Reliable queue: the payload stays in the processing list until
                # it is executed, so a failure never loses the decision.
                raw = await self._redis_client.client.blmove(
                    self._queue_key,
                    _PROCESSING_KEY,
                    1,
                    "RIGHT",
                    "LEFT",
                )
                if not raw:
                    await asyncio.sleep(0.1)
                    continue
                await self._handle_payload(cast("str", raw))
            except Exception:
                logger.exception(
                    "ExecutionLoop encountered an error, continuing",
                    extra={
                        "loop": "execution",
                        "queue_key": self._queue_key,
                    },
                )
                await asyncio.sleep(0.1)

    async def _recover_in_flight(self) -> None:
        """Requeue payloads left in the processing list by a crashed run."""
        client = self._redis_client.client
        recovered = 0
        while await client.lmove(_PROCESSING_KEY, self._queue_key, "LEFT", "RIGHT"):
            recovered += 1
        if recovered:
            logger.warning(
                "Requeued %d in-flight decisions from a previous run",
                recovered,
                extra={"loop": "execution", "recovered": recovered},
            )

    async def _handle_payload(self, raw: str) -> None:
        try:
            decision = DecisionMessageSchema.model_validate_json(raw)
        except Exception:
            logger.exception(
                "Failed to parse decision payload from queue %s",
                self._queue_key,
                extra={"loop": "execution", "queue_key": self._queue_key},
            )
            await self._dead_letter(raw)
            return
        try:
            await self._execute_decision(decision)
        except Exception:
            attempts = self._attempts.get(decision.decision_id, 0) + 1
            self._attempts[decision.decision_id] = attempts
            logger.exception(
                "Execution of decision %s failed (attempt %d/%d)",
                decision.decision_id,
                attempts,
                _MAX_DECISION_ATTEMPTS,
                extra={
                    "loop": "execution",
                    "decision_id": decision.decision_id,
                    "symbol": decision.symbol,
                },
            )
            if attempts >= _MAX_DECISION_ATTEMPTS:
                self._attempts.pop(decision.decision_id, None)
                await self._dead_letter(raw)
                return
            # Push back before removing so a crash in between duplicates
            # rather than loses the decision.
            client = self._redis_client.client
            await client.rpush(self._queue_key, raw)
            await client.lrem(_PROCESSING_KEY, 1, raw)
            return
        self._attempts.pop(decision.decision_id, None)
        await self._redis_client.client.lrem(_PROCESSING_KEY, 1, raw)

    async def _dead_letter(self, raw: str) -> None:
        client = self._redis_client.client
        await client.lpush(_FAILED_KEY, raw)
        await client.lrem(_PROCESSING_KEY, 1, raw)
        logger.error(
            "Decision moved to %s",
            _FAILED_KEY,
            extra={"loop": "execution", "payload_preview": raw[:200]},
        )

    async def _execute_decision(self, decision: DecisionMessageSchema) -> None:
        logger.info(
            "Decision dequeued: id=%s symbol=%s action=%s",
            decision.decision_id,
            decision.symbol,
            decision.action,
            extra={
                "decision_id": decision.decision_id,
                "symbol": decision.symbol,
            },
        )
        position_snapshot: PositionSchema | None = None
        if decision.action == "CLOSE":
            position_snapshot = await self._state_manager.get_position(
                decision.symbol,
            )
        result = await self._engine.execute(decision)
        logger.info(
            "Execution result: id=%s status=%s qty=%s price=%s",
            decision.decision_id,
            result.status,
            result.executed_qty,
            result.executed_price,
            extra={
                "decision_id": decision.decision_id,
                "status": result.status,
            },
        )
        try:
            await self._report_execution(decision, result)
        except Exception:
            logger.exception(
                "Failed to report execution for %s",
                decision.symbol,
                extra={
                    "loop": "execution",
                    "decision_id": decision.decision_id,
                    "symbol": decision.symbol,
                    "status": result.status,
                },
            )
        if (
            position_snapshot is not None
            and result.status == "FILLED"
            and result.executed_price is not None
        ):
            await self._safe_report_position_close(
                position_snapshot,
                "Brain decision",
                Decimal(str(result.executed_price)),
            )

    async def _maybe_sweep_pending_entries(self) -> None:
        """Run the pending-entry sweep at most once per sweep interval."""
        now_ms = int(utc_now().timestamp() * 1000)
        if now_ms - self._last_pending_sweep_ms < _PENDING_SWEEP_INTERVAL_MS:
            return
        self._last_pending_sweep_ms = now_ms
        try:
            await self._engine.process_pending_entries(now_ms)
        except Exception:
            logger.exception("Pending-entry sweep failed, continuing")

    async def _report_execution(
        self,
        decision: DecisionMessageSchema,
        result: ExecutionResultSchema,
    ) -> None:
        if self._report_populator is None:
            return
        await self._report_populator.record_trade(
            symbol=decision.symbol,
            side=decision.action,
            status=result.status,
            confidence=decision.calibrated_confidence,
            entry_price=decision.entry_price,
            quantity=Decimal(str(result.executed_qty))
            if result.executed_qty
            else decision.quantity,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            reasoning=result.error_message or decision.reasoning,
        )

    async def _safe_report_position_close(
        self,
        position: PositionSchema,
        close_reason: str,
        exit_price: Decimal,
    ) -> None:
        if self._report_populator is None:
            return
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
                close_reason=close_reason,
                leverage=position.leverage,
                opened_at=position.opened_at,
            )
        except Exception:
            logger.exception(
                "Failed to report position close for %s",
                position.symbol,
                extra={
                    "loop": "execution",
                    "position_id": position.id,
                    "symbol": position.symbol,
                    "close_reason": close_reason,
                },
            )
