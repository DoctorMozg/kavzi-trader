from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis  # type: ignore[import-untyped]

from kavzi_trader.events.config import EventStoreConfigSchema
from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.spine.state.config import RedisConfigSchema
from kavzi_trader.spine.state.redis_client import RedisStateClient


class DummyRedisClient:
    def __init__(self) -> None:
        self.xadd = AsyncMock(return_value="1-0")
        self.xrange = AsyncMock(return_value=[])
        self.xdel = AsyncMock(return_value=1)


class DummyRedisStateClient(RedisStateClient):
    def __init__(self) -> None:
        super().__init__(RedisConfigSchema())
        self._client = cast("Redis", DummyRedisClient())


@pytest.mark.asyncio
async def test_store_append_calls_xadd() -> None:
    redis_client = DummyRedisStateClient()
    store = RedisEventStore(redis_client, EventStoreConfigSchema())
    event = EventSchema(
        event_id="event-1",
        event_type="order_created",
        version=1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        aggregate_id="order-1",
        aggregate_type="orders",
        data={},
        metadata={},
    )

    event_id = await store.append(event)

    assert event_id == "1-0"
    redis_client.client.xadd.assert_called_once()


@pytest.mark.asyncio
async def test_store_read_returns_events() -> None:
    redis_client = DummyRedisStateClient()
    store = RedisEventStore(redis_client, EventStoreConfigSchema())
    event = EventSchema(
        event_id="event-1",
        event_type="order_created",
        version=1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        aggregate_id="order-1",
        aggregate_type="orders",
        data={},
        metadata={},
    )
    redis_client.client.xrange.return_value = [
        (
            "1-0",
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "version": "1",
                "timestamp": event.timestamp.isoformat(),
                "aggregate_id": event.aggregate_id,
                "aggregate_type": event.aggregate_type,
                "data": "{}",
                "metadata": "{}",
            },
        ),
    ]

    events = await store.read("kt:events:orders")

    assert len(events) == 1
    assert events[0].event_id == event.event_id
