import logging

from pydantic import ValidationError

from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)

POSITION_KEY_PREFIX = "kt:state:positions"
POSITION_INDEX_KEY = "kt:state:positions:index"


class PositionStore:
    def __init__(self, redis_client: RedisStateClient) -> None:
        self._redis = redis_client

    def _position_key(self, position_id: str) -> str:
        return f"{POSITION_KEY_PREFIX}:{position_id}"

    def _parse_position(self, key: str, data: dict[str, str]) -> PositionSchema | None:
        try:
            return PositionSchema.model_validate_json(data["data"])
        except (ValidationError, KeyError):
            logger.exception("Corrupt position data in Redis key %s", key)
            return None

    async def get(self, position_id: str) -> PositionSchema | None:
        key = self._position_key(position_id)
        data = await self._redis.hgetall(key)
        if not data:
            return None
        return self._parse_position(key, data)

    async def get_by_symbol(self, symbol: str) -> PositionSchema | None:
        positions = await self.get_all()
        for position in positions:
            if position.symbol == symbol:
                return position
        return None

    async def get_all(self) -> list[PositionSchema]:
        position_ids = await self._redis.smembers(POSITION_INDEX_KEY)
        if not position_ids:
            return []

        keys = [self._position_key(pid) for pid in position_ids]
        pipe = self._redis.pipeline()
        for key in keys:
            pipe.hgetall(key)
        results: list[dict[str, str]] = await pipe.execute()

        positions: list[PositionSchema] = []
        stale_ids: list[str] = []
        for pid, key, data in zip(position_ids, keys, results, strict=True):
            if not data:
                stale_ids.append(pid)
                continue
            position = self._parse_position(key, data)
            if position is not None:
                positions.append(position)

        # Clean up index entries that point to missing hash keys
        if stale_ids:
            logger.warning(
                "Removing %d stale entries from position index: %s",
                len(stale_ids),
                stale_ids,
            )
            await self._redis.srem(POSITION_INDEX_KEY, *stale_ids)

        return positions

    async def save(self, position: PositionSchema) -> None:
        key = self._position_key(position.id)
        await self._redis.hset(key, {"data": position.model_dump_json()})
        await self._redis.sadd(POSITION_INDEX_KEY, position.id)
        logger.debug("Saved position %s for %s", position.id, position.symbol)

    async def delete(self, position_id: str) -> None:
        await self._redis.delete(self._position_key(position_id))
        await self._redis.srem(POSITION_INDEX_KEY, position_id)
        logger.debug("Deleted position %s", position_id)

    async def clear_all(self) -> int:
        position_ids = await self._redis.smembers(POSITION_INDEX_KEY)
        for pid in position_ids:
            await self._redis.delete(self._position_key(pid))
        await self._redis.delete(POSITION_INDEX_KEY)
        logger.info("Cleared %d positions from Redis", len(position_ids))
        return len(position_ids)

    async def count(self) -> int:
        return await self._redis.scard(POSITION_INDEX_KEY)
