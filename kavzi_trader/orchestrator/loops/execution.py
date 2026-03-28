from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Literal

from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.execution_result_schema import ExecutionResultSchema
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


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

    async def run(self) -> None:
        logger.info(
            "ExecutionLoop started, listening on queue %s",
            self._queue_key,
        )
        while True:
            try:
                item = await self._redis_client.client.brpop(
                    self._queue_key,
                    timeout=1,
                )
                if not item:
                    await asyncio.sleep(0.1)
                    continue
                try:
                    decision = DecisionMessageSchema.model_validate_json(item[1])
                except Exception:
                    logger.exception("Failed to parse decision payload")
                    continue
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
            except Exception:
                logger.exception("ExecutionLoop encountered an error, continuing")
                await asyncio.sleep(0.1)

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
            )
