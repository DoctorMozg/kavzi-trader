from kavzi_trader.events.event_schema import EventSchema


class ConfidenceProjection:
    """Tracks decision confidence outcomes."""

    def __init__(self) -> None:
        self._decisions: dict[str, dict[str, object | None]] = {}

    def apply(self, event: EventSchema) -> None:
        if event.aggregate_type != "decisions":
            return
        self._decisions[event.aggregate_id] = dict(event.data)

    def snapshot(self) -> dict[str, dict[str, object | None]]:
        return dict(self._decisions)
