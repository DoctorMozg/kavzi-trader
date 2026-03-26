import logging

from redis.asyncio import Redis  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class ConfidenceHistoryStore:
    """
    Persists confidence outcomes in Redis to compute historical accuracy.
    """

    def __init__(self, redis: Redis, key_prefix: str = "kt:brain:confidence") -> None:
        self._redis = redis
        self._key_prefix = key_prefix

    async def record(self, bucket: str, was_correct: bool) -> None:
        key = f"{self._key_prefix}:{bucket}"
        await self._redis.hincrby(key, "total", 1)
        if was_correct:
            await self._redis.hincrby(key, "correct", 1)
        logger.debug(
            "Recorded outcome: bucket=%s correct=%s",
            bucket,
            was_correct,
        )

    async def get_accuracy(self, bucket: str) -> float | None:
        key = f"{self._key_prefix}:{bucket}"
        data = await self._redis.hgetall(key)
        total_value = data.get(b"total") or data.get("total")
        correct_value = data.get(b"correct") or data.get("correct")
        if total_value is None:
            return None
        total = int(total_value)
        if total == 0:
            return None
        correct = int(correct_value or 0)
        accuracy = correct / total
        logger.debug(
            "Accuracy for bucket %s: %d/%d = %.3f",
            bucket,
            correct,
            total,
            accuracy,
        )
        return accuracy
