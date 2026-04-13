from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.spine.state.config import RedisConfigSchema
from kavzi_trader.spine.state.redis_client import RedisStateClient


class TestRedisStateClientExecutePipeline:
    @pytest.fixture
    def client(self, redis_config: RedisConfigSchema) -> RedisStateClient:
        return RedisStateClient(redis_config)

    async def test_execute_pipeline_invokes_builder_and_returns_results(
        self,
        client: RedisStateClient,
    ):
        mock_pipe = MagicMock()
        mock_pipe.hset = MagicMock()
        mock_pipe.sadd = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, 1])

        mock_underlying = MagicMock()
        mock_underlying.pipeline = MagicMock(return_value=mock_pipe)
        client._client = mock_underlying

        calls: list[object] = []

        def builder(pipe):
            calls.append(pipe)
            pipe.hset("k", mapping={"data": "v"})
            pipe.sadd("idx", "id1")

        result = await client.execute_pipeline(builder)

        assert result == [1, 1]
        assert calls == [mock_pipe]
        mock_pipe.hset.assert_called_once_with("k", mapping={"data": "v"})
        mock_pipe.sadd.assert_called_once_with("idx", "id1")
        mock_pipe.execute.assert_awaited_once()
