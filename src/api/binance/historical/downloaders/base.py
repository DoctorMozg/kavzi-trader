"""
Base downloader for historical data.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Generic, TypeVar

import dateparser
from pydantic import BaseModel

from src.api.binance.client import BinanceClient
from src.api.binance.historical.data_saver import DataSaver
from src.commons.time_utility import utc_now

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseDownloader(Generic[T]):
    """Base class for historical data downloaders."""

    def __init__(self, client: BinanceClient) -> None:
        """
        Initialize the BaseDownloader.

        Args:
            client: BinanceClient instance
        """
        self.client = client
        self.data_saver: DataSaver = DataSaver()

    def parse_time(
        self,
        time_value: str | datetime | None,
        default: datetime | None = None,
    ) -> datetime:
        """
        Parse a time value to datetime.

        Args:
            time_value: Time value to parse
            default: Default value if time_value is None

        Returns:
            Parsed datetime
        """
        if time_value is None:
            if default is None:
                return utc_now()
            return default

        if isinstance(time_value, datetime):
            return time_value

        parsed_time = dateparser.parse(time_value)
        if not parsed_time:
            raise ValueError(f"Could not parse time: {time_value}")
        return parsed_time

    async def execute_parallel_downloads(
        self,
        batches: list[dict[str, Any]],
        download_func: Callable[..., Awaitable[list[T]]],
        max_workers: int,
        save_progress: bool,
        symbol: str,
        data_type: str,
        interval: str | None = None,
        output_dir: Path | None = None,
    ) -> list[T]:
        """
        Execute parallel downloads for batches using asyncio.

        Args:
            batches: List of batch configurations
            download_func: Async function to download a single batch
            max_workers: Maximum number of concurrent workers (semaphore limit)
            save_progress: Whether to save each batch as it completes
            symbol: Trading pair symbol
            data_type: Type of data (klines, trades, etc.)
            interval: Kline interval if applicable
            output_dir: Directory to save data

        Returns:
            List of downloaded data
        """
        all_data: list[T] = []
        
        # Create a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_workers)
        
        async def download_with_semaphore(batch_config: dict[str, Any], batch_index: int) -> tuple[list[T], dict[str, Any], int]:
            """Download a batch with semaphore control."""
            async with semaphore:
                try:
                    # Call the download function with the batch parameters
                    batch_data = await download_func(**batch_config)
                    return batch_data, batch_config, batch_index
                except Exception as e:
                    logger.exception(
                        "Error downloading batch %s to %s: %s",
                        batch_config.get("start_time"),
                        batch_config.get("end_time"),
                        str(e),
                    )
                    return [], batch_config, batch_index

        # Create tasks for all batches
        tasks = [
            download_with_semaphore(batch, i)
            for i, batch in enumerate(batches)
        ]
        
        # Execute all tasks concurrently and process results as they complete
        total_batches = len(batches)
        completed = 0
        
        for task in asyncio.as_completed(tasks):
            batch_data, batch, _ = await task
            completed += 1
            
            if batch_data:
                all_data.extend(batch_data)
                
                # Save batch data if requested
                if save_progress:
                    self.data_saver.save_data(
                        data=batch_data,
                        symbol=symbol,
                        data_type=data_type,
                        interval=interval,
                        start_time=batch.get("start_time"),
                        end_time=batch.get("end_time"),
                        output_dir=output_dir,
                    )
            
            logger.info(
                "Completed batch %d/%d for %s %s (%.1f%%)",
                completed,
                total_batches,
                symbol,
                data_type + (f" {interval}" if interval else ""),
                (completed / total_batches) * 100,
            )

        return all_data
