import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class OrderFlowFetcher(Protocol):
    async def fetch(self) -> None: ...


class OrderFlowLoop:
    """Periodically refreshes order flow data for configured symbols."""

    def __init__(self, fetcher: OrderFlowFetcher, interval_s: int) -> None:
        self._fetcher = fetcher
        self._interval_s = interval_s

    async def run(self) -> None:
        logger.info(
            "OrderFlowLoop started, interval=%ds", self._interval_s,
        )
        while True:
            try:
                logger.debug("OrderFlowLoop fetching order flow data")
                await self._fetcher.fetch()
                logger.debug(
                    "OrderFlowLoop fetch complete, sleeping %ds",
                    self._interval_s,
                )
            except Exception:
                logger.exception("OrderFlowLoop encountered an error, continuing")
            await asyncio.sleep(self._interval_s)
