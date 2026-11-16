import logging

from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.orchestrator.loops.decision_queue import DECISION_QUEUE_KEY
from kavzi_trader.strategies.tick_result_schema import StrategyIntent

logger = logging.getLogger(__name__)


class DecisionPublisher:
    """Queues a strategy intent for the execution loop."""

    def __init__(self, redis_client: RedisStateClient) -> None:
        self._redis_client = redis_client

    async def publish(self, intent: StrategyIntent) -> bool:
        """Push the intent to the execution queue; True only if it was queued."""
        try:
            await self._redis_client.client.lpush(
                DECISION_QUEUE_KEY,
                intent.model_dump_json(),
            )
        except Exception:
            logger.exception(
                "Failed to enqueue decision for %s",
                intent.symbol,
                extra={
                    "loop": "reasoning",
                    "symbol": intent.symbol,
                    "decision_id": intent.decision_id,
                    "action": intent.action,
                    "queue_key": DECISION_QUEUE_KEY,
                },
            )
            return False
        logger.info(
            "Enqueuing decision for %s: action=%s confidence=%.2f decision_id=%s",
            intent.symbol,
            intent.action,
            intent.raw_confidence,
            intent.decision_id,
            extra={
                "symbol": intent.symbol,
                "decision_id": intent.decision_id,
                "action": intent.action,
            },
        )
        return True
