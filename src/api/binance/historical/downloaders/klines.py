"""
Klines downloader for historical data.
"""

import logging
from datetime import datetime

from src.api.binance.client import BinanceClient
from src.api.binance.historical.batch import (
    BatchProcessor,
    SymbolicDownloadBatchConfigSchema,
)
from src.api.binance.historical.downloaders.base import BaseDownloader
from src.api.common.exceptions import APIError, RateLimitError
from src.api.common.models import CandlestickSchema
from src.commons.time_utility import milliseconds_to_datetime

logger = logging.getLogger(__name__)


class KlinesDownloader(BaseDownloader[CandlestickSchema]):
    """Downloader for historical klines data."""

    def __init__(self, client: BinanceClient) -> None:
        """Initialize the KlinesDownloader."""
        super().__init__(client)

    async def download(
        self,
        config: SymbolicDownloadBatchConfigSchema,
    ) -> list[CandlestickSchema]:
        """
        Download historical klines (candlestick) data.

        Args:
            config: Configuration for the download batch with symbol

        Returns:
            List of candlestick data
        """
        # Process input parameters
        start_time_dt = config.start_time
        end_time_dt = config.end_time

        # Get batch intervals
        batches = BatchProcessor.get_kline_batch_intervals(
            start_time=start_time_dt,
            end_time=end_time_dt,
            interval=config.interval,
            batch_size=config.batch_size,
        )

        logger.info(
            "Starting download of %s %s klines from %s to %s (%d batches)",
            config.symbol,
            config.interval,
            start_time_dt,
            end_time_dt,
            len(batches),
        )

        # Convert batch times from milliseconds to datetime for the download function
        download_batches = [
            {
                "symbol": config.symbol,
                "interval": config.interval,
                "start_time": milliseconds_to_datetime(batch["start_time"]),
                "end_time": milliseconds_to_datetime(batch["end_time"]),
            }
            for batch in batches
        ]

        # Execute parallel downloads
        all_data = await self.execute_parallel_downloads(
            batches=download_batches,
            download_func=self._download_batch,
            max_workers=config.max_workers,
            symbol=config.symbol,
            data_type="klines",
            interval=config.interval,
        )

        logger.info(
            "Completed download of %s %s klines: %d records retrieved",
            config.symbol,
            config.interval,
            len(all_data),
        )

        return all_data

    async def _download_batch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CandlestickSchema]:
        """
        Download a batch of klines.

        Args:
            symbol: Trading pair symbol
            interval: Kline interval
            start_time: Start time for the batch
            end_time: End time for the batch

        Returns:
            List of candlestick data
        """
        try:
            # Get klines using the standard client
            klines = await self.client.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                limit=1000,  # Maximum allowed by Binance
            )
        except RateLimitError as e:
            raise APIError("Rate limit hit") from e
        except APIError:
            logger.exception("API error downloading klines")
            raise
        else:
            return klines
