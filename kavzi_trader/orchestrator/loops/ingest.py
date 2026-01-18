from typing import Protocol


class StreamManager(Protocol):
    async def start(self) -> None: ...


class DataIngestLoop:
    """Runs the WebSocket stream manager for market data ingestion."""

    def __init__(self, stream_manager: StreamManager) -> None:
        self._stream_manager = stream_manager

    async def run(self) -> None:
        await self._stream_manager.start()
