from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.spine.state.position_store import (
    POSITION_INDEX_KEY,
    POSITION_KEY_PREFIX,
    PositionStore,
)
from kavzi_trader.spine.state.schemas import PositionSchema


class TestPositionStore:
    @pytest.fixture
    def store(self, mock_redis_client: AsyncMock) -> PositionStore:
        store = PositionStore.__new__(PositionStore)
        store._redis = mock_redis_client
        return store

    async def test_save_position(
        self,
        store: PositionStore,
        sample_position: PositionSchema,
    ):
        await store.save(sample_position)

        store._redis.hset.assert_called_once()
        call_args = store._redis.hset.call_args
        assert f"{POSITION_KEY_PREFIX}:pos_123" == call_args[0][0]
        store._redis.sadd.assert_called_once_with(POSITION_INDEX_KEY, "pos_123")

    async def test_get_position_found(
        self,
        store: PositionStore,
        sample_position: PositionSchema,
    ):
        store._redis.hgetall.return_value = {"data": sample_position.model_dump_json()}

        result = await store.get("pos_123")

        assert result is not None
        assert result.id == "pos_123"
        assert result.symbol == "BTCUSDT"

    async def test_get_position_not_found(self, store: PositionStore):
        store._redis.hgetall.return_value = {}

        result = await store.get("nonexistent")

        assert result is None

    async def test_get_by_symbol(
        self,
        store: PositionStore,
        sample_position: PositionSchema,
    ):
        mock_pipe = MagicMock()
        mock_pipe.hgetall = MagicMock()
        mock_pipe.execute = AsyncMock(
            return_value=[{"data": sample_position.model_dump_json()}],
        )
        store._redis.smembers = AsyncMock(return_value={"pos_123"})
        store._redis.pipeline = MagicMock(return_value=mock_pipe)

        result = await store.get_by_symbol("BTCUSDT")

        assert result is not None
        assert result.symbol == "BTCUSDT"

    async def test_get_by_symbol_not_found(
        self,
        store: PositionStore,
        sample_position: PositionSchema,
    ):
        mock_pipe = MagicMock()
        mock_pipe.hgetall = MagicMock()
        mock_pipe.execute = AsyncMock(
            return_value=[{"data": sample_position.model_dump_json()}],
        )
        store._redis.smembers = AsyncMock(return_value={"pos_123"})
        store._redis.pipeline = MagicMock(return_value=mock_pipe)

        result = await store.get_by_symbol("ETHUSDT")

        assert result is None

    async def test_get_all_positions(
        self,
        store: PositionStore,
        sample_position: PositionSchema,
        sample_position_short: PositionSchema,
    ):
        mock_pipe = MagicMock()
        mock_pipe.hgetall = MagicMock()
        mock_pipe.execute = AsyncMock(
            return_value=[
                {"data": sample_position.model_dump_json()},
                {"data": sample_position_short.model_dump_json()},
            ],
        )
        store._redis.smembers = AsyncMock(return_value={"pos_123", "pos_456"})
        store._redis.pipeline = MagicMock(return_value=mock_pipe)

        result = await store.get_all()

        assert len(result) == 2
        symbols = {p.symbol for p in result}
        assert symbols == {"BTCUSDT", "ETHUSDT"}

    async def test_get_all_empty(self, store: PositionStore):
        store._redis.smembers = AsyncMock(return_value=set())

        result = await store.get_all()

        assert result == []

    async def test_get_all_cleans_stale_index_entries(
        self,
        store: PositionStore,
    ):
        mock_pipe = MagicMock()
        mock_pipe.hgetall = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[{}])
        store._redis.smembers = AsyncMock(return_value={"pos_gone"})
        store._redis.pipeline = MagicMock(return_value=mock_pipe)
        store._redis.srem = AsyncMock()

        result = await store.get_all()

        assert result == []
        store._redis.srem.assert_called_once_with(POSITION_INDEX_KEY, "pos_gone")

    async def test_delete_position(self, store: PositionStore):
        await store.delete("pos_123")

        store._redis.delete.assert_called_once_with(f"{POSITION_KEY_PREFIX}:pos_123")
        store._redis.srem.assert_called_once_with(POSITION_INDEX_KEY, "pos_123")

    async def test_count_positions(self, store: PositionStore):
        store._redis.scard = AsyncMock(return_value=2)

        count = await store.count()

        assert count == 2
