import logging

from pydantic import ValidationError

from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)

POSITION_KEY_PREFIX = "kt:state:positions"


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
        keys = await self._redis.keys(f"{POSITION_KEY_PREFIX}:*")
        positions = []
        for key in keys:
            data = await self._redis.hgetall(key)
            if data:
                position = self._parse_position(key, data)
                if position is not None:
                    positions.append(position)
        return positions

    async def save(self, position: PositionSchema) -> None:
        key = self._position_key(position.id)
        await self._redis.hset(key, {"data": position.model_dump_json()})
        logger.debug("Saved position %s for %s", position.id, position.symbol)

    async def delete(self, position_id: str) -> None:
        await self._redis.delete(self._position_key(position_id))
        logger.debug("Deleted position %s", position_id)

    async def count(self) -> int:
        keys = await self._redis.keys(f"{POSITION_KEY_PREFIX}:*")
        return len(keys)
