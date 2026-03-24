import asyncio
import logging

from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.state.redis_client import RedisStateClient

logger = logging.getLogger(__name__)


class ExecutionLoop:
    """Consumes queued decisions and executes orders."""

    def __init__(
        self,
        redis_client: RedisStateClient,
        engine: ExecutionEngine,
        queue_key: str = "kt:decisions:pending",
    ) -> None:
        self._redis_client = redis_client
        self._engine = engine
        self._queue_key = queue_key

    async def run(self) -> None:
        while True:
            try:
                item = await self._redis_client.client.brpop(
                    self._queue_key, timeout=1,
                )
                if not item:
                    await asyncio.sleep(0.1)
                    continue
                try:
                    decision = DecisionMessageSchema.model_validate_json(item[1])
                except Exception:
                    logger.exception("Failed to parse decision payload")
                    continue
                await self._engine.execute(decision)
            except Exception:
                logger.exception("ExecutionLoop encountered an error, continuing")
                await asyncio.sleep(0.1)
