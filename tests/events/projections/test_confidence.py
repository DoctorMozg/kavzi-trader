from datetime import UTC, datetime

from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.projections.confidence import ConfidenceProjection


def test_confidence_projection_updates_snapshot() -> None:
    projection = ConfidenceProjection()
    event = EventSchema(
        event_id="event-1",
        event_type="decision_logged",
        version=1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        aggregate_id="decision-1",
        aggregate_type="decisions",
        data={"confidence": 0.7},
        metadata={},
    )

    projection.apply(event)
    snapshot = projection.snapshot()

    assert snapshot["decision-1"]["confidence"] == 0.7
