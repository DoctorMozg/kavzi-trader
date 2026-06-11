import logging

from pydantic import ValidationError

from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import PendingEntrySchema

logger = logging.getLogger(__name__)

PENDING_ENTRY_KEY_PREFIX = "kt:state:pending_entries"


class PendingEntryStore:
    """Redis-backed store of resting PULLBACK entry limits, keyed by order id."""

    def __init__(self, redis_client: RedisStateClient) -> None:
        self._redis = redis_client

    def _key(self, order_id: str) -> str:
        return f"{PENDING_ENTRY_KEY_PREFIX}:{order_id}"

    def _parse(self, key: str, data: dict[str, str]) -> PendingEntrySchema | None:
        try:
            return PendingEntrySchema.model_validate_json(data["data"])
        except (ValidationError, KeyError):
            logger.exception("Corrupt pending-entry data in Redis key %s", key)
            return None

    async def get_all(self) -> list[PendingEntrySchema]:
        keys = await self._redis.keys(f"{PENDING_ENTRY_KEY_PREFIX}:*")
        entries: list[PendingEntrySchema] = []
        for key in keys:
            data = await self._redis.hgetall(key)
            if data:
                entry = self._parse(key, data)
                if entry is not None:
                    entries.append(entry)
        return entries

    async def save(self, entry: PendingEntrySchema) -> None:
        key = self._key(entry.order_id)
        await self._redis.hset(key, {"data": entry.model_dump_json()})
        logger.debug("Saved pending entry %s for %s", entry.order_id, entry.symbol)

    async def delete(self, order_id: str) -> None:
        await self._redis.delete(self._key(order_id))
        logger.debug("Deleted pending entry %s", order_id)

    async def clear_all(self) -> int:
        keys = await self._redis.keys(f"{PENDING_ENTRY_KEY_PREFIX}:*")
        for key in keys:
            await self._redis.delete(key)
        logger.info("Cleared %d pending entries from Redis", len(keys))
        return len(keys)
