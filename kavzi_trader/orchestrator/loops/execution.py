from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import cast

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.decision_message import DecisionMessageSchema
from kavzi_trader.domain.execution_result import ExecutionResultSchema
from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.orchestrator.loops.decision_queue import DECISION_QUEUE_KEY
from kavzi_trader.orchestrator.loops.position_close_reporter import (
    PositionCloseReporter,
)
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.strategies.bracket_intent_schema import BracketIntentSchema
from kavzi_trader.strategies.strategy_intent import (
    STRATEGY_INTENT_ADAPTER,
    intent_id,
)
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)
from kavzi_trader.ui.recorder import UiEventRecorder

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
        ui_recorder: UiEventRecorder | None = None,
    ) -> None:
        self._redis_client = redis_client
        self._engine = engine
        self._state_manager = state_manager
        self._ui_recorder = ui_recorder
        self._close_reporter = PositionCloseReporter(ui_recorder, "execution")
        self._last_pending_sweep_ms = 0
        self._attempts: dict[str, int] = {}

    async def run(self) -> None:
        logger.info(
            "ExecutionLoop started, listening on queue %s",
            DECISION_QUEUE_KEY,
        )
        await self._recover_in_flight()
        while True:
            try:
                await self._maybe_sweep_pending_entries()
                # Reliable queue: the payload stays in the processing list until
                # it is executed, so a failure never loses the decision.
                raw = await self._redis_client.client.blmove(
                    DECISION_QUEUE_KEY,
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
                        "queue_key": DECISION_QUEUE_KEY,
                    },
                )
                await asyncio.sleep(0.1)

    async def _recover_in_flight(self) -> None:
        """Requeue payloads left in the processing list by a crashed run."""
        client = self._redis_client.client
        recovered = 0
        while await client.lmove(_PROCESSING_KEY, DECISION_QUEUE_KEY, "LEFT", "RIGHT"):
            recovered += 1
        if recovered:
            logger.warning(
                "Requeued %d in-flight decisions from a previous run",
                recovered,
                extra={"loop": "execution", "recovered": recovered},
            )

    async def _handle_payload(self, raw: str) -> None:
        try:
            intent = STRATEGY_INTENT_ADAPTER.validate_json(raw)
        except Exception:
            logger.exception(
                "Failed to parse decision payload from queue %s",
                DECISION_QUEUE_KEY,
                extra={"loop": "execution", "queue_key": DECISION_QUEUE_KEY},
            )
            await self._dead_letter(raw)
            return
        key = intent_id(intent)
        try:
            await self._route(intent)
        except Exception:
            attempts = self._attempts.get(key, 0) + 1
            self._attempts[key] = attempts
            logger.exception(
                "Execution of %s intent %s failed (attempt %d/%d)",
                intent.kind,
                key,
                attempts,
                _MAX_DECISION_ATTEMPTS,
                extra={
                    "loop": "execution",
                    "decision_id": key,
                    "symbol": intent.symbol,
                },
            )
            if attempts >= _MAX_DECISION_ATTEMPTS:
                self._attempts.pop(key, None)
                await self._dead_letter(raw)
                return
            # Push back before removing so a crash in between duplicates
            # rather than loses the decision.
            client = self._redis_client.client
            await client.rpush(DECISION_QUEUE_KEY, raw)
            await client.lrem(_PROCESSING_KEY, 1, raw)
            return
        self._attempts.pop(key, None)
        await self._redis_client.client.lrem(_PROCESSING_KEY, 1, raw)

    async def _route(
        self, intent: BracketIntentSchema | TargetWeightIntentSchema
    ) -> None:
        if isinstance(intent, TargetWeightIntentSchema):
            await self._execute_rebalance(intent)
        else:
            await self._execute_decision(intent)

    async def _execute_rebalance(self, intent: TargetWeightIntentSchema) -> None:
        logger.info(
            "Target-weight intent dequeued: id=%s symbol=%s weight=%s",
            intent.intent_id,
            intent.symbol,
            intent.target_weight,
            extra={"intent_id": intent.intent_id, "symbol": intent.symbol},
        )
        result = await self._engine.rebalance.execute(intent)
        logger.info(
            "Rebalance result: id=%s status=%s qty=%s price=%s reason=%s",
            intent.intent_id,
            result.status,
            result.executed_qty,
            result.executed_price,
            result.error_message,
            extra={"intent_id": intent.intent_id, "status": result.status},
        )

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
            await self._close_reporter.report(
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
        if self._ui_recorder is None:
            return
        await self._ui_recorder.record_trade(decision, result)
