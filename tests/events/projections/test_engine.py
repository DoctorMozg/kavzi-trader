from datetime import UTC, datetime

from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.projections.engine import ProjectionEngine


def test_projection_engine_dispatches() -> None:
    engine = ProjectionEngine()
    calls = []

    def handler(event: EventSchema) -> None:
        calls.append(event.event_type)

    engine.register(handler)
    engine.apply(
        EventSchema(
            event_id="event-1",
            event_type="order_created",
            version=1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            aggregate_id="order-1",
            aggregate_type="orders",
            data={},
            metadata={},
        ),
    )

    assert calls == ["order_created"]
