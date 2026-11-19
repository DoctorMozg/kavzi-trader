from datetime import date

from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.strategies.trend.trend_halving_schema import TrendHalvingSchema
from kavzi_trader.strategies.trend.trend_state_schema import TrendStateSchema

STATE_KEY = "kt:strategy:trend:state"
_DAY_FIELD = "last_rebalance_day"
_WEIGHT_PREFIX = "weight:"
_HALVING_PREFIX = "halving:"


class TrendStateStore:
    """Persists the rebalance day, last-set weights and halvings in one Redis hash."""

    def __init__(self, redis_client: RedisStateClient) -> None:
        self._redis = redis_client

    async def load(self) -> TrendStateSchema:
        raw = await self._redis.hgetall(STATE_KEY)
        day = raw.get(_DAY_FIELD)
        return TrendStateSchema(
            last_rebalance_day=date.fromisoformat(day) if day else None,
            weights={
                field.removeprefix(_WEIGHT_PREFIX): float(value)
                for field, value in raw.items()
                if field.startswith(_WEIGHT_PREFIX)
            },
            halvings={
                field.removeprefix(_HALVING_PREFIX): (
                    TrendHalvingSchema.model_validate_json(value)
                )
                for field, value in raw.items()
                if field.startswith(_HALVING_PREFIX)
            },
        )

    async def save_day(self, day: date) -> None:
        await self._redis.hset(STATE_KEY, {_DAY_FIELD: day.isoformat()})

    async def save_weight(self, symbol: str, weight: float) -> None:
        await self._redis.hset(STATE_KEY, {f"{_WEIGHT_PREFIX}{symbol}": repr(weight)})

    async def save_halving(self, halving: TrendHalvingSchema) -> None:
        await self._redis.hset(
            STATE_KEY, {f"{_HALVING_PREFIX}{halving.symbol}": halving.model_dump_json()}
        )

    async def clear_halvings(self, symbols: list[str]) -> None:
        if symbols:
            await self._redis.hdel(
                STATE_KEY, *(f"{_HALVING_PREFIX}{s}" for s in symbols)
            )
