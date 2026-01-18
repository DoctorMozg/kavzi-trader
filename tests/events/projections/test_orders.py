from datetime import UTC, datetime

from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.projections.orders import OrdersProjection


def test_orders_projection_updates_snapshot() -> None:
    projection = OrdersProjection()
    event = EventSchema(
        event_id="event-1",
        event_type="order_created",
        version=1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        aggregate_id="order-1",
        aggregate_type="orders",
        data={"symbol": "BTCUSDT"},
        metadata={},
    )

    projection.apply(event)
    snapshot = projection.snapshot()

    assert snapshot["order-1"]["symbol"] == "BTCUSDT"
