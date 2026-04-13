from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

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
        mock_pipe = MagicMock()
        mock_pipe.hset = MagicMock()
        mock_pipe.sadd = MagicMock()

        async def fake_execute(builder):
            builder(mock_pipe)
            return [1, 1]

        store._redis.execute_pipeline = AsyncMock(side_effect=fake_execute)

        await store.save(sample_position)

        store._redis.execute_pipeline.assert_called_once()
        mock_pipe.hset.assert_called_once()
        hset_args = mock_pipe.hset.call_args
        assert hset_args[0][0] == f"{POSITION_KEY_PREFIX}:pos_123"
        assert "mapping" in hset_args[1]
        assert "data" in hset_args[1]["mapping"]
        mock_pipe.sadd.assert_called_once_with(POSITION_INDEX_KEY, "pos_123")

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
        mock_pipe = MagicMock()
        mock_pipe.delete = MagicMock()
        mock_pipe.srem = MagicMock()

        async def fake_execute(builder):
            builder(mock_pipe)
            return [1, 1]

        store._redis.execute_pipeline = AsyncMock(side_effect=fake_execute)

        await store.delete("pos_123")

        store._redis.execute_pipeline.assert_called_once()
        mock_pipe.delete.assert_called_once_with(f"{POSITION_KEY_PREFIX}:pos_123")
        mock_pipe.srem.assert_called_once_with(POSITION_INDEX_KEY, "pos_123")

    async def test_save_atomic_across_reconnect(
        self,
        store: PositionStore,
        sample_position: PositionSchema,
    ):
        """Transient connection drop during save must retry and end with both
        hash and index applied — not a partial state."""
        pipe_first = MagicMock()
        pipe_first.hset = MagicMock()
        pipe_first.sadd = MagicMock()
        pipe_first.execute = AsyncMock(side_effect=RedisConnectionError("drop"))

        pipe_second = MagicMock()
        pipe_second.hset = MagicMock()
        pipe_second.sadd = MagicMock()
        pipe_second.execute = AsyncMock(return_value=[1, 1])

        pipes = iter([pipe_first, pipe_second])

        async def fake_execute_pipeline(builder):
            # Simulate the real execute_pipeline: rebuild pipeline on retry,
            # reapply the builder each attempt.
            last_error: Exception | None = None
            for _ in range(2):
                pipe = next(pipes)
                builder(pipe)
                try:
                    return await pipe.execute()
                except RedisConnectionError as exc:
                    last_error = exc
            raise last_error  # pragma: no cover

        store._redis.execute_pipeline = AsyncMock(side_effect=fake_execute_pipeline)

        await store.save(sample_position)

        # Builder must have re-run against the fresh pipeline: both commands
        # are staged on the second pipeline that actually executed.
        pipe_second.hset.assert_called_once()
        pipe_second.sadd.assert_called_once_with(POSITION_INDEX_KEY, "pos_123")
        pipe_second.execute.assert_awaited_once()

    async def test_delete_atomic_across_reconnect(self, store: PositionStore):
        pipe_first = MagicMock()
        pipe_first.delete = MagicMock()
        pipe_first.srem = MagicMock()
        pipe_first.execute = AsyncMock(side_effect=RedisConnectionError("drop"))

        pipe_second = MagicMock()
        pipe_second.delete = MagicMock()
        pipe_second.srem = MagicMock()
        pipe_second.execute = AsyncMock(return_value=[1, 1])

        pipes = iter([pipe_first, pipe_second])

        async def fake_execute_pipeline(builder):
            last_error: Exception | None = None
            for _ in range(2):
                pipe = next(pipes)
                builder(pipe)
                try:
                    return await pipe.execute()
                except RedisConnectionError as exc:
                    last_error = exc
            raise last_error  # pragma: no cover

        store._redis.execute_pipeline = AsyncMock(side_effect=fake_execute_pipeline)

        await store.delete("pos_123")

        pipe_second.delete.assert_called_once_with(f"{POSITION_KEY_PREFIX}:pos_123")
        pipe_second.srem.assert_called_once_with(POSITION_INDEX_KEY, "pos_123")
        pipe_second.execute.assert_awaited_once()

    async def test_count_positions(self, store: PositionStore):
        store._redis.scard = AsyncMock(return_value=2)

        count = await store.count()

        assert count == 2
