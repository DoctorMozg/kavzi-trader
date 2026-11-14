from typing import Protocol

from kavzi_trader.ui.event_schemas import UiEvent


class UiPublisher(Protocol):
    """Best-effort sink for dashboard events; must never raise into trading."""

    async def publish(self, event: UiEvent) -> None: ...
