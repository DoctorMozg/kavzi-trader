"""
Base downloader for historical data.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple

from pydantic import BaseModel

from kavzi_trader.api.binance.client import BinanceClient

logger = logging.getLogger(__name__)


class BaseDownloader[T: BaseModel]:
    """
    Base class for historical data downloaders.

    Implements common functionality for downloading historical data with support for:
    - Parallel downloads using asyncio
    - Batching to maximize throughput and minimize API rate limiting
    - Progress tracking
    """

    def __init__(self, client: BinanceClient) -> None:
        """
        Initialize the BaseDownloader.

        Args:
            client: BinanceClient instance
        """
        self.client = client

    async def execute_parallel_downloads(
        self,
        batches: list[dict[str, Any]],
        download_func: Callable[..., Awaitable[list[T]]],
        max_workers: int,
        symbol: str,
        data_type: str,
        interval: str | None = None,
    ) -> list[T]:
        """
        Execute parallel downloads for batches using asyncio.

        Args:
            batches: List of batch configurations
            download_func: Async function to download a single batch
            max_workers: Maximum number of concurrent workers (semaphore limit)
            symbol: Trading pair symbol
            data_type: Type of data (klines, trades, etc.)
            interval: Kline interval if applicable

        Returns:
            List of downloaded data
        """
        all_data: list[T] = []

        # Create a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_workers)

        class _DownloadBatchResult(NamedTuple):
            data: list[Any]
            config: dict[str, Any]
            batch_index: int

        async def download_with_semaphore(
            batch_config: dict[str, Any],
            batch_index: int,
        ) -> _DownloadBatchResult:
            """Download a batch with semaphore control."""
            async with semaphore:
                try:
                    # Call the download function with the batch parameters
                    batch_data = await download_func(**batch_config)
                except Exception:
                    logger.exception(
                        "Error downloading batch %s to %s",
                        batch_config.get("start_time"),
                        batch_config.get("end_time"),
                    )
                    return _DownloadBatchResult(
                        data=[],
                        config=batch_config,
                        batch_index=batch_index,
                    )
                else:
                    return _DownloadBatchResult(
                        data=batch_data,
                        config=batch_config,
                        batch_index=batch_index,
                    )

        # Create tasks for all batches
        tasks = [download_with_semaphore(batch, i) for i, batch in enumerate(batches)]

        # Execute all tasks concurrently and process results as they complete
        total_batches = len(batches)

        for completed, task in enumerate(asyncio.as_completed(tasks)):
            batch_result = await task

            if batch_result.data:
                all_data.extend(batch_result.data)

            logger.info(
                "Completed batch %d/%d for %s %s (%.1f%%)",
                completed + 1,
                total_batches,
                symbol,
                data_type + (f" {interval}" if interval else ""),
                (completed / total_batches) * 100,
            )

        return all_data
