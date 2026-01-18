from kavzi_trader.events.event_schema import EventSchema


class PositionsProjection:
    """Materialized view of position lifecycle events."""

    def __init__(self) -> None:
        self._positions: dict[str, dict[str, object | None]] = {}

    def apply(self, event: EventSchema) -> None:
        if event.aggregate_type != "positions":
            return
        self._positions[event.aggregate_id] = dict(event.data)

    def snapshot(self) -> dict[str, dict[str, object | None]]:
        return dict(self._positions)
