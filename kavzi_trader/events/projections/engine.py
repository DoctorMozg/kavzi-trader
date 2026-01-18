from collections.abc import Callable

from kavzi_trader.events.event_schema import EventSchema


class ProjectionEngine:
    """Dispatches events to registered projection handlers."""

    def __init__(self) -> None:
        self._handlers: list[Callable[[EventSchema], None]] = []

    def register(self, handler: Callable[[EventSchema], None]) -> None:
        self._handlers.append(handler)

    def apply(self, event: EventSchema) -> None:
        for handler in self._handlers:
            handler(event)
