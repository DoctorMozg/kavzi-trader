from kavzi_trader.infra.redis_client import RedisStateClient

KEY_PREFIX = "kt:strategy:trend:hourly_rv:"


class HourlyVarianceStore:
    """Keeps each symbol's hourly realized variance, so restarts skip the backfill."""

    def __init__(self, redis_client: RedisStateClient) -> None:
        self._redis = redis_client

    async def load(self, symbol: str) -> dict[int, float]:
        raw = await self._redis.hgetall(KEY_PREFIX + symbol)
        return {int(hour): float(rv) for hour, rv in raw.items()}

    async def save(self, symbol: str, rv_by_hour: dict[int, float]) -> None:
        if rv_by_hour:
            await self._redis.hset(
                KEY_PREFIX + symbol, {str(h): repr(rv) for h, rv in rv_by_hour.items()}
            )

    async def drop(self, symbol: str, hours: list[int]) -> None:
        if hours:
            await self._redis.hdel(KEY_PREFIX + symbol, *map(str, hours))
