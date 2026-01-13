import logging
from typing import Any, cast

from redis.asyncio import Redis  # type: ignore[import-untyped]

from kavzi_trader.spine.state.config import RedisConfigSchema

logger = logging.getLogger(__name__)


class RedisStateClient:
    def __init__(self, config: RedisConfigSchema) -> None:
        self._config = config
        self._client: Redis | None = None  # type: ignore[type-arg]

    async def connect(self) -> None:
        self._client = Redis(
            host=self._config.host,
            port=self._config.port,
            db=self._config.db,
            password=self._config.password,
            decode_responses=True,
        )
        await self._client.ping()
        logger.info(
            "Connected to Redis at %s:%d",
            self._config.host,
            self._config.port,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Disconnected from Redis")

    @property
    def client(self) -> Redis:  # type: ignore[type-arg]
        if self._client is None:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._client

    async def hset(self, key: str, mapping: dict[str, Any]) -> None:
        await self.client.hset(key, mapping=mapping)

    async def hget(self, key: str, field: str) -> str | None:
        result = await self.client.hget(key, field)
        return cast(str | None, result)

    async def hgetall(self, key: str) -> dict[str, str]:
        result = await self.client.hgetall(key)
        return cast(dict[str, str], result) if result else {}

    async def hdel(self, key: str, *fields: str) -> int:
        result = await self.client.hdel(key, *fields)
        return cast(int, result)

    async def delete(self, key: str) -> int:
        result = await self.client.delete(key)
        return cast(int, result)

    async def keys(self, pattern: str) -> list[str]:
        result = await self.client.keys(pattern)
        return cast(list[str], result)

    async def set(self, key: str, value: str) -> None:
        await self.client.set(key, value)

    async def get(self, key: str) -> str | None:
        result = await self.client.get(key)
        return cast(str | None, result)
