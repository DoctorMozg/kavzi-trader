import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class StreamManager(Protocol):
    async def start(self) -> None: ...


class DataIngestLoop:
    """Runs the WebSocket stream manager for market data ingestion."""

    def __init__(self, stream_manager: StreamManager) -> None:
        self._stream_manager = stream_manager

    async def run(self) -> None:
        while True:
            try:
                await self._stream_manager.start()
            except Exception:
                logger.exception("DataIngestLoop encountered an error, restarting")
                await asyncio.sleep(1)
