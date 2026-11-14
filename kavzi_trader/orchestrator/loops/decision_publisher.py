import logging
from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.brain.agent.router import PipelineResult
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.orchestrator.loops.decision_message_builder import (
    DecisionMessageBuilder,
)
from kavzi_trader.orchestrator.loops.decision_queue import DECISION_QUEUE_KEY

logger = logging.getLogger(__name__)


class DecisionPublisher:
    """Builds the decision message for a pipeline result and queues it for execution."""

    def __init__(
        self,
        redis_client: RedisStateClient,
        builder: DecisionMessageBuilder,
    ) -> None:
        self._redis_client = redis_client
        self.builder = builder

    async def publish(
        self,
        result: PipelineResult,
        size_multiplier: Decimal = Decimal(1),
    ) -> bool:
        """Push the decision to the execution queue; True only if it was queued."""
        if result.trader is None or result.trader_deps is None:
            return False
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        decision = self.builder.build(
            result.trader,
            result.trader_deps,
            now_ms,
            geometry=result.geometry,
            size_multiplier=size_multiplier,
        )
        symbol = result.trader_deps.symbol
        if decision is None:
            logger.warning(
                "Skipping enqueue for %s: decision message could not be"
                " built from Trader output (see prior error log)",
                symbol,
                extra={"symbol": symbol},
            )
            return False
        try:
            await self._redis_client.client.lpush(
                DECISION_QUEUE_KEY,
                decision.model_dump_json(),
            )
        except Exception:
            logger.exception(
                "Failed to enqueue decision for %s",
                symbol,
                extra={
                    "loop": "reasoning",
                    "symbol": symbol,
                    "decision_id": decision.decision_id,
                    "action": decision.action,
                    "queue_key": DECISION_QUEUE_KEY,
                },
            )
            return False
        logger.info(
            "Enqueuing decision for %s: action=%s confidence=%.2f decision_id=%s",
            symbol,
            decision.action,
            decision.raw_confidence,
            decision.decision_id,
            extra={
                "symbol": symbol,
                "decision_id": decision.decision_id,
                "action": decision.action,
            },
        )
        return True
