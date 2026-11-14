from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from redis.asyncio import Redis

from kavzi_trader.events.aggregate_type import (
    AggregateType,
    UnknownAggregateTypeError,
)
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
        aggregate_type=AggregateType.ORDERS,
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
        aggregate_type=AggregateType.ORDERS,
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


@pytest.mark.asyncio
async def test_store_routes_each_aggregate_type_to_its_stream() -> None:
    config = EventStoreConfigSchema()
    redis_client = DummyRedisStateClient()
    store = RedisEventStore(redis_client, config)

    for aggregate_type, stream in config.streams.items():
        await store.append(
            EventSchema(
                event_type="probe",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                aggregate_id="a-1",
                aggregate_type=aggregate_type,
            ),
        )

        assert redis_client.client.xadd.await_args.args[0] == stream


def test_event_rejects_unknown_aggregate_type() -> None:
    with pytest.raises(ValidationError, match="aggregate_type"):
        EventSchema.model_validate(
            {
                "event_type": "probe",
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                "aggregate_id": "a-1",
                "aggregate_type": "position",
            },
        )


@pytest.mark.asyncio
async def test_store_raises_when_aggregate_type_has_no_stream() -> None:
    redis_client = DummyRedisStateClient()
    store = RedisEventStore(redis_client, EventStoreConfigSchema(streams={}))
    event = EventSchema(
        event_type="probe",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        aggregate_id="a-1",
        aggregate_type=AggregateType.POSITIONS,
    )

    with pytest.raises(UnknownAggregateTypeError, match="positions"):
        await store.append(event)

    redis_client.client.xadd.assert_not_called()
