"""
Trades downloader for historical data.
"""

import logging
import time
from datetime import datetime
from pathlib import Path

from src.api.binance.client import BinanceClient
from src.api.binance.historical.batch import BatchProcessor
from src.api.binance.historical.downloaders.base import BaseDownloader
from src.api.common.models import TradeSchema
from src.commons.time_utility import MILLISECONDS_IN_SECOND

logger = logging.getLogger(__name__)


class TradesDownloader(BaseDownloader[TradeSchema]):
    """Downloader for historical trades data."""

    def __init__(self, client: BinanceClient) -> None:
        """Initialize the TradesDownloader."""
        super().__init__(client)

    def download(
        self,
        symbol: str,
        start_time: str | datetime,
        end_time: str | datetime | None = None,
        max_workers: int = 4,
        output_dir: Path | None = None,
        save_progress: bool = True,
    ) -> list[TradeSchema]:
        """
        Download historical trades data.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            start_time: Start time for the download (string or datetime)
            end_time: End time for the download (string or datetime, defaults to now)
            max_workers: Maximum number of concurrent workers
            output_dir: Directory to save data
            save_progress: Whether to save each batch as it completes

        Returns:
            List of trade data
        """
        # Process input parameters
        start_time_dt = self.parse_time(start_time)
        end_time_dt = self.parse_time(end_time)

        # Get batch intervals
        batches = BatchProcessor.get_trade_batch_intervals(
            start_time=start_time_dt,
            end_time=end_time_dt,
        )

        logger.info(
            "Starting download of %s trades from %s to %s (%d batches)",
            symbol,
            start_time_dt,
            end_time_dt,
            len(batches),
        )

        # Prepare download batches
        download_batches = [
            {
                "symbol": symbol,
                "start_time": batch["start_time"],
                "end_time": batch["end_time"],
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
            data_type="trades",
            output_dir=output_dir,
        )

        logger.info(
            "Completed download of %s trades: %d records retrieved",
            symbol,
            len(all_data),
        )

        # Save all data if requested and not already saved by batch
        if all_data and not save_progress:
            self.data_saver.save_data(
                data=all_data,
                symbol=symbol,
                data_type="trades",
                start_time=start_time_dt,
                end_time=end_time_dt,
                output_dir=output_dir,
            )

        return all_data

    def _download_batch(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[TradeSchema]:
        """
        Download a batch of trades.

        Args:
            symbol: Trading pair symbol
            start_time: Start time for the batch
            end_time: End time for the batch

        Returns:
            List of trade data
        """
        max_iterations = 100  # Safety limit for iterations
        # Convert times to milliseconds
        start_ms = int(start_time.timestamp() * MILLISECONDS_IN_SECOND)
        end_ms = int(end_time.timestamp() * MILLISECONDS_IN_SECOND)

        # First, get trades around our start time
        first_trades = self.client.get_historical_trades(
            symbol=symbol,
            limit=1,
            start_time=start_ms,
        )

        if not first_trades:
            return []

        from_id = first_trades[0].id
        all_trades = []

        # Keep fetching trades until we reach the end time
        iteration_count = 0
        while iteration_count < max_iterations:
            iteration_count += 1
            batch = self.client.get_historical_trades(
                symbol=symbol,
                limit=1000,
                from_id=from_id,
            )

            if not batch:
                break

            # Filter trades by time
            valid_trades = [
                t
                for t in batch
                if start_ms
                <= int(t.time.timestamp() * MILLISECONDS_IN_SECOND)
                <= end_ms
            ]

            all_trades.extend(valid_trades)

            # Check if we've reached the end time
            last_trade_time = int(batch[-1].time.timestamp() * MILLISECONDS_IN_SECOND)
            if last_trade_time > end_ms:
                break

            # Safety check for tests - if from_id doesn't change, we're in a loop
            next_from_id = batch[-1].id + 1
            if next_from_id == from_id:
                # We're not making progress, likely in a test with mocked data
                logger.warning(
                    "Trade ID not advancing, breaking loop at iteration %d",
                    iteration_count,
                )
                break

            # Update from_id for next iteration
            from_id = next_from_id

            # Avoid rate limiting
            time.sleep(0.1)

        # Check if we hit the max iteration limit
        if iteration_count >= max_iterations:
            logger.warning(
                "Reached maximum iteration limit (%d) when downloading trades",
                max_iterations,
            )

        return all_trades
