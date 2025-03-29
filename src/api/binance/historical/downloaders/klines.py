"""
Klines downloader for historical data.
"""

import logging
from datetime import datetime
from pathlib import Path

from src.api.binance.client import BinanceClient
from src.api.binance.historical.batch import BatchProcessor
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

    def download(
        self,
        symbol: str,
        interval: str,
        start_time: str | datetime,
        end_time: str | datetime | None = None,
        batch_size: int = 1000,
        max_workers: int = 4,
        output_dir: Path | None = None,
        save_progress: bool = True,
    ) -> list[CandlestickSchema]:
        """
        Download historical klines (candlestick) data.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            interval: Kline interval (e.g., "1m", "1h", "1d")
            start_time: Start time for the download (string or datetime)
            end_time: End time for the download (string or datetime, defaults to now)
            batch_size: Size of each download batch
            max_workers: Maximum number of concurrent workers
            output_dir: Directory to save data
            save_progress: Whether to save each batch as it completes

        Returns:
            List of candlestick data
        """
        # Process input parameters
        start_time_dt = self.parse_time(start_time)
        end_time_dt = self.parse_time(end_time)

        # Get batch intervals
        batches = BatchProcessor.get_kline_batch_intervals(
            start_time=start_time_dt,
            end_time=end_time_dt,
            interval=interval,
            batch_size=batch_size,
        )

        logger.info(
            "Starting download of %s %s klines from %s to %s (%d batches)",
            symbol,
            interval,
            start_time_dt,
            end_time_dt,
            len(batches),
        )

        # Convert batch times from milliseconds to datetime for the download function
        download_batches = [
            {
                "symbol": symbol,
                "interval": interval,
                "start_time": milliseconds_to_datetime(batch["start_time"]),
                "end_time": milliseconds_to_datetime(batch["end_time"]),
            }
            for batch in batches
        ]

        # Execute parallel downloads
        all_data = self.execute_parallel_downloads(
            batches=download_batches,
            download_func=self._download_batch,
            max_workers=max_workers,
            save_progress=save_progress,
            symbol=symbol,
            data_type="klines",
            interval=interval,
            output_dir=output_dir,
        )

        logger.info(
            "Completed download of %s %s klines: %d records retrieved",
            symbol,
            interval,
            len(all_data),
        )

        # Save all data if requested and not already saved by batch
        if all_data and not save_progress:
            self.data_saver.save_data(
                data=all_data,
                symbol=symbol,
                data_type="klines",
                interval=interval,
                start_time=start_time_dt,
                end_time=end_time_dt,
                output_dir=output_dir,
            )

        return all_data

    def _download_batch(
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
            klines = self.client.get_klines(
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
