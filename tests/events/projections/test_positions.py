from datetime import UTC, datetime

from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.projections.positions import PositionsProjection


def test_positions_projection_updates_snapshot() -> None:
    projection = PositionsProjection()
    event = EventSchema(
        event_id="event-1",
        event_type="position_opened",
        version=1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        aggregate_id="pos-1",
        aggregate_type="positions",
        data={"symbol": "ETHUSDT"},
        metadata={},
    )

    projection.apply(event)
    snapshot = projection.snapshot()

    assert snapshot["pos-1"]["symbol"] == "ETHUSDT"
