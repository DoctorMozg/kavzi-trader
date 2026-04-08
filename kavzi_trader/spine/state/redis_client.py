from __future__ import annotations

import asyncio
import builtins
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import TypeVar, cast

import redis.asyncio  # type: ignore[import-untyped]
import redis.asyncio.client  # type: ignore[import-untyped]
from redis.asyncio import Redis  # type: ignore[import-untyped]
from redis.exceptions import (
    ConnectionError as RedisConnectionError,  # type: ignore[import-untyped]
)
from redis.exceptions import RedisError  # type: ignore[import-untyped]
from redis.exceptions import TimeoutError as RedisTimeoutError

from kavzi_trader.spine.state.config import RedisConfigSchema

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRYABLE = (RedisConnectionError, RedisTimeoutError, ConnectionResetError, OSError)


class RedisStateClient:
    def __init__(self, config: RedisConfigSchema) -> None:
        self._config = config
        self._client: Redis | None = None  # type: ignore[type-arg]
        self._retry_attempts = config.retry_attempts
        self._retry_backoff_s = config.retry_backoff_s

    async def connect(self) -> None:
        self._client = Redis(
            host=self._config.host,
            port=self._config.port,
            db=self._config.db,
            password=self._config.password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        await self._client.ping()
        logger.info(
            "Connected to Redis at %s:%d",
            self._config.host,
            self._config.port,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Disconnected from Redis")

    @property
    def client(self) -> Redis:  # type: ignore[type-arg]
        if self._client is None:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._client

    async def _retry(
        self,
        operation: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T:
        """Execute a Redis operation with retry on transient failures."""
        last_error: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await operation(*args, **kwargs)
            except _RETRYABLE as exc:
                last_error = exc
                if attempt < self._retry_attempts:
                    delay = self._retry_backoff_s * attempt
                    logger.warning(
                        "Redis operation failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt,
                        self._retry_attempts,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    await self._reconnect()
            except RedisError as exc:
                logger.exception("Non-retryable Redis error")
                raise RedisStateError(str(exc)) from exc
        msg = (
            f"Redis operation failed after {self._retry_attempts} attempts: "
            f"{last_error}"
        )
        raise RedisStateError(msg)

    async def _reconnect(self) -> None:
        """Attempt to re-establish the Redis connection."""
        try:
            if self._client:
                await self._client.close()
            self._client = Redis(
                host=self._config.host,
                port=self._config.port,
                db=self._config.db,
                password=self._config.password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            await self._client.ping()
            logger.info("Reconnected to Redis")
        except Exception:
            logger.exception("Redis reconnection failed")

    async def hset(self, key: str, mapping: dict[str, object]) -> None:
        normalized = {field: str(value) for field, value in mapping.items()}
        payload = cast(
            "Mapping[str | bytes, bytes | float | int | str]",
            normalized,
        )
        await self._retry(self.client.hset, key, mapping=payload)

    async def hget(self, key: str, field: str) -> str | None:
        result = await self._retry(self.client.hget, key, field)
        return cast("str | None", result)

    async def hgetall(self, key: str) -> dict[str, str]:
        result = await self._retry(self.client.hgetall, key)
        return cast("dict[str, str]", result) if result else {}

    async def hdel(self, key: str, *fields: str) -> int:
        result = await self._retry(self.client.hdel, key, *fields)
        return cast("int", result)

    async def delete(self, key: str) -> int:
        result = await self._retry(self.client.delete, key)
        return cast("int", result)

    async def keys(self, pattern: str) -> list[str]:
        result = await self._retry(self.client.keys, pattern)
        return cast("list[str]", result)

    async def set(self, key: str, value: str) -> None:
        await self._retry(self.client.set, key, value)

    async def get(self, key: str) -> str | None:
        result = await self._retry(self.client.get, key)
        return cast("str | None", result)

    async def sadd(self, key: str, *members: str) -> int:
        result = await self._retry(self.client.sadd, key, *members)
        return cast("int", result)

    async def srem(self, key: str, *members: str) -> int:
        result = await self._retry(self.client.srem, key, *members)
        return cast("int", result)

    async def smembers(self, key: str) -> builtins.set[str]:
        result = await self._retry(self.client.smembers, key)
        return cast("set[str]", result)

    async def scard(self, key: str) -> int:
        result = await self._retry(self.client.scard, key)
        return cast("int", result)

    def pipeline(self) -> redis.asyncio.client.Pipeline:  # type: ignore[type-arg]
        """Return a pipeline bound to the current connection."""
        return self.client.pipeline()

    async def ping(self) -> bool:
        try:
            await self.client.ping()
        except RedisError:
            return False
        return True


class RedisStateError(Exception):
    """Raised when a Redis state operation fails after retries."""
