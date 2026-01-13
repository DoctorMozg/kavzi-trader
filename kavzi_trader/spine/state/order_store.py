import logging

from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import OpenOrderSchema

logger = logging.getLogger(__name__)

ORDER_KEY_PREFIX = "kt:state:orders"


class OrderStore:
    def __init__(self, redis_client: RedisStateClient) -> None:
        self._redis = redis_client

    def _order_key(self, order_id: str) -> str:
        return f"{ORDER_KEY_PREFIX}:{order_id}"

    async def get(self, order_id: str) -> OpenOrderSchema | None:
        data = await self._redis.hgetall(self._order_key(order_id))
        if not data:
            return None
        return OpenOrderSchema.model_validate_json(data["data"])

    async def get_by_symbol(self, symbol: str) -> list[OpenOrderSchema]:
        orders = await self.get_all()
        return [order for order in orders if order.symbol == symbol]

    async def get_by_position(self, position_id: str) -> list[OpenOrderSchema]:
        orders = await self.get_all()
        return [order for order in orders if order.linked_position_id == position_id]

    async def get_all(self) -> list[OpenOrderSchema]:
        keys = await self._redis.keys(f"{ORDER_KEY_PREFIX}:*")
        orders = []
        for key in keys:
            data = await self._redis.hgetall(key)
            if data:
                orders.append(OpenOrderSchema.model_validate_json(data["data"]))
        return orders

    async def save(self, order: OpenOrderSchema) -> None:
        key = self._order_key(order.order_id)
        await self._redis.hset(key, {"data": order.model_dump_json()})
        logger.debug("Saved order %s for %s", order.order_id, order.symbol)

    async def delete(self, order_id: str) -> None:
        await self._redis.delete(self._order_key(order_id))
        logger.debug("Deleted order %s", order_id)

    async def count(self) -> int:
        keys = await self._redis.keys(f"{ORDER_KEY_PREFIX}:*")
        return len(keys)
