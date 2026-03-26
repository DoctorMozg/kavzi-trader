from unittest.mock import AsyncMock

import pytest

from kavzi_trader.spine.state.order_store import ORDER_KEY_PREFIX, OrderStore
from kavzi_trader.spine.state.schemas import OpenOrderSchema


class TestOrderStore:
    @pytest.fixture
    def store(self, mock_redis_client: AsyncMock) -> OrderStore:
        store = OrderStore.__new__(OrderStore)
        store._redis = mock_redis_client
        return store

    async def test_save_order(
        self,
        store: OrderStore,
        sample_order: OpenOrderSchema,
    ):
        await store.save(sample_order)

        store._redis.hset.assert_called_once()
        call_args = store._redis.hset.call_args
        assert f"{ORDER_KEY_PREFIX}:order_789" == call_args[0][0]

    async def test_get_order_found(
        self,
        store: OrderStore,
        sample_order: OpenOrderSchema,
    ):
        store._redis.hgetall.return_value = {"data": sample_order.model_dump_json()}

        result = await store.get("order_789")

        assert result is not None
        assert result.order_id == "order_789"

    async def test_get_order_not_found(self, store: OrderStore):
        store._redis.hgetall.return_value = {}

        result = await store.get("nonexistent")

        assert result is None

    async def test_get_by_symbol(
        self,
        store: OrderStore,
        sample_order: OpenOrderSchema,
    ):
        store._redis.keys.return_value = [f"{ORDER_KEY_PREFIX}:order_789"]
        store._redis.hgetall.return_value = {"data": sample_order.model_dump_json()}

        result = await store.get_by_symbol("BTCUSDT")

        assert len(result) == 1
        assert result[0].symbol == "BTCUSDT"

    async def test_get_by_position(
        self,
        store: OrderStore,
        sample_sl_order: OpenOrderSchema,
    ):
        store._redis.keys.return_value = [f"{ORDER_KEY_PREFIX}:order_sl_001"]
        store._redis.hgetall.return_value = {"data": sample_sl_order.model_dump_json()}

        result = await store.get_by_position("pos_123")

        assert len(result) == 1
        assert result[0].linked_position_id == "pos_123"

    async def test_get_all_orders(
        self,
        store: OrderStore,
        sample_order: OpenOrderSchema,
        sample_sl_order: OpenOrderSchema,
    ):
        store._redis.keys.return_value = [
            f"{ORDER_KEY_PREFIX}:order_789",
            f"{ORDER_KEY_PREFIX}:order_sl_001",
        ]
        store._redis.hgetall.side_effect = [
            {"data": sample_order.model_dump_json()},
            {"data": sample_sl_order.model_dump_json()},
        ]

        result = await store.get_all()

        assert len(result) == 2

    async def test_delete_order(self, store: OrderStore):
        await store.delete("order_789")

        store._redis.delete.assert_called_once_with(f"{ORDER_KEY_PREFIX}:order_789")

    async def test_count_orders(self, store: OrderStore):
        store._redis.keys.return_value = [
            f"{ORDER_KEY_PREFIX}:order_1",
            f"{ORDER_KEY_PREFIX}:order_2",
            f"{ORDER_KEY_PREFIX}:order_3",
        ]

        count = await store.count()

        assert count == 3
