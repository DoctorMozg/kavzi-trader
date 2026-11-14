import asyncio

from kavzi_trader.ui.event_schemas import UiEvent
from kavzi_trader.ui.redis_publisher import EVENT_FIELD

type Entry = tuple[str, dict[str, str]]


class FakeUiRedis:
    """In-memory stand-in for the XADD/XRANGE/XREAD subset the UI uses."""

    def __init__(self) -> None:
        self.streams: dict[str, list[Entry]] = {}
        self.closed = False
        self._counter = 0
        self._new_data = asyncio.Event()

    def add(self, stream: str, event: UiEvent) -> None:
        self.add_raw(stream, {EVENT_FIELD: event.model_dump_json()})

    def add_raw(self, stream: str, fields: dict[str, str]) -> None:
        self._counter += 1
        self.streams.setdefault(stream, []).append((f"{self._counter}-0", fields))
        self._new_data.set()

    async def xrange(self, name: str) -> list[Entry]:
        return list(self.streams.get(name, []))

    async def xrevrange(self, name: str, count: int) -> list[Entry]:
        return list(reversed(self.streams.get(name, [])))[:count]

    async def xread(
        self,
        streams: dict[str, str],
        count: int,
        block: int,
    ) -> list[tuple[str, list[Entry]]]:
        result = self._after(streams, count)
        if not result:
            self._new_data.clear()
            try:
                await asyncio.wait_for(self._new_data.wait(), block / 1000)
            except TimeoutError:
                return []
            result = self._after(streams, count)
        return result

    async def aclose(self) -> None:
        self.closed = True

    def _after(
        self,
        streams: dict[str, str],
        count: int,
    ) -> list[tuple[str, list[Entry]]]:
        result = []
        for name, last_id in streams.items():
            last = int(last_id.split("-")[0])
            newer = [
                e for e in self.streams.get(name, []) if int(e[0].split("-")[0]) > last
            ]
            if newer:
                result.append((name, newer[:count]))
        return result
