from datetime import UTC, datetime

from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.serialization import deserialize_event, serialize_event


def test_serialization_roundtrip() -> None:
    event = EventSchema(
        event_id="event-1",
        event_type="order_created",
        version=1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        aggregate_id="order-1",
        aggregate_type="orders",
        data={"symbol": "BTCUSDT", "price": 100},
        metadata={"source": "test"},
    )

    fields = serialize_event(event)
    restored = deserialize_event(fields)

    assert restored.event_id == event.event_id
    assert restored.event_type == event.event_type
    assert restored.aggregate_id == event.aggregate_id
    assert restored.aggregate_type == event.aggregate_type
    assert restored.data == event.data
    assert restored.metadata == event.metadata
