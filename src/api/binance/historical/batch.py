"""
Batch processing utilities for historical data downloads.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from src.api.binance.constants import KLINE_INTERVALS
from src.commons.time_utility import MILLISECONDS_IN_SECOND

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class DownloadBatchConfigSchema(BaseModel):
    """Base configuration for a download batch without symbol."""

    interval: str = ""  # Empty for trades
    start_time: datetime
    end_time: datetime
    batch_size: int = Field(default=1000, gt=0)
    max_workers: int = Field(default=4, gt=0)


class SymbolicDownloadBatchConfigSchema(DownloadBatchConfigSchema):
    """Configuration for a download batch with a specific symbol."""

    symbol: str  # Required for specific symbol


class BatchProcessor:
    """Handles batch processing for historical data downloads."""

    @staticmethod
    def get_kline_batch_intervals(
        start_time: datetime,
        end_time: datetime,
        interval: str,
        batch_size: int,
    ) -> list[dict[str, Any]]:
        """
        Split a time range into batches for efficient kline downloading.

        Args:
            start_time: Start time for the download
            end_time: End time for the download
            interval: Kline interval (e.g., "1m", "1h", "1d")
            batch_size: Maximum number of records per batch

        Returns:
            List of batch configurations with start_time and end_time
        """
        # Convert interval to milliseconds
        interval_ms = KLINE_INTERVALS.get(interval, 60) * MILLISECONDS_IN_SECOND

        # Calculate batch duration based on interval and batch size
        batch_duration_ms = interval_ms * batch_size

        # Convert datetime to milliseconds
        start_ms = int(start_time.timestamp() * MILLISECONDS_IN_SECOND)
        end_ms = int(end_time.timestamp() * MILLISECONDS_IN_SECOND)

        # Create batch intervals
        batches = []
        batch_start = start_ms

        while batch_start < end_ms:
            batch_end = min(batch_start + batch_duration_ms, end_ms)
            batches.append(
                {
                    "start_time": batch_start,
                    "end_time": batch_end,
                },
            )
            batch_start = batch_end + 1  # Avoid overlap

        return batches

    @staticmethod
    def get_trade_batch_intervals(
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, datetime]]:
        """
        Split a time range into daily batches for efficient trade downloading.

        Args:
            start_time: Start time for the download
            end_time: End time for the download

        Returns:
            List of batch configurations with start_time and end_time
        """
        # Split the time range into days
        batches = []
        current_start = start_time

        while current_start < end_time:
            current_end = min(current_start + timedelta(days=1), end_time)
            batches.append(
                {
                    "start_time": current_start,
                    "end_time": current_end,
                },
            )
            current_start = current_end

        return batches
