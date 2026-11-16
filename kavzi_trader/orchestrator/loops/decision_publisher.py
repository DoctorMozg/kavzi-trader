import logging

from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.orchestrator.loops.decision_queue import DECISION_QUEUE_KEY
from kavzi_trader.strategies.strategy_intent import StrategyIntent, intent_id

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
                "Failed to enqueue %s intent for %s",
                intent.kind,
                intent.symbol,
                extra={
                    "loop": "strategy",
                    "symbol": intent.symbol,
                    "kind": intent.kind,
                    "intent_id": intent_id(intent),
                    "queue_key": DECISION_QUEUE_KEY,
                },
            )
            return False
        logger.info(
            "Enqueued %s intent for %s: id=%s",
            intent.kind,
            intent.symbol,
            intent_id(intent),
            extra={
                "symbol": intent.symbol,
                "kind": intent.kind,
                "intent_id": intent_id(intent),
            },
        )
        return True
