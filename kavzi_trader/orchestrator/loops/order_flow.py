import asyncio
from typing import Protocol


class OrderFlowFetcher(Protocol):
    async def fetch(self) -> None: ...


class OrderFlowLoop:
    """Periodically refreshes order flow data for configured symbols."""

    def __init__(self, fetcher: OrderFlowFetcher, interval_s: int) -> None:
        self._fetcher = fetcher
        self._interval_s = interval_s

    async def run(self) -> None:
        while True:
            await self._fetcher.fetch()
            await asyncio.sleep(self._interval_s)
