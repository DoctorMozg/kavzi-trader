"""
Data saving utilities for historical data downloads.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Generic, TypeVar

import pandas as pd
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class DataSaver(Generic[T]):
    """Handles saving downloaded data to files."""

    def __init__(self, output_dir: Path = Path("./data")) -> None:
        """
        Initialize the DataSaver.

        Args:
            output_dir: Directory to save data
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_data(
        self,
        data: list[T],
        symbol: str,
        data_type: str,
        interval: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        output_dir: Path | None = None,
    ) -> Path:
        """
        Save data to a CSV file.

        Args:
            data: Data to save
            symbol: Trading pair symbol
            data_type: Type of data (klines, trades, etc.)
            interval: Kline interval if applicable
            start_time: Start time for the data
            end_time: End time for the data
            output_dir: Directory to save data (defaults to self.output_dir)

        Returns:
            Path to the saved file
        """
        if not data:
            logger.warning("No data to save for %s %s", symbol, data_type)
            return Path()  # Return empty Path to match return type

        # Use defaults if not specified
        dir_to_use = output_dir or self.output_dir

        # Create directory if it doesn't exist
        dir_to_use.mkdir(parents=True, exist_ok=True)

        # Create filename based on data type and time range
        time_suffix = ""
        if start_time and end_time:
            time_suffix = (
                f"{start_time.strftime('%Y%m%d')}_to_{end_time.strftime('%Y%m%d')}"
            )

        interval_part = f"_{interval}" if interval else ""
        filename_base = f"{symbol}_{data_type}{interval_part}_{time_suffix}"

        # Create pandas DataFrame from data
        data_df = pd.DataFrame([item.model_dump() for item in data])

        # Save to CSV
        filepath = dir_to_use / f"{filename_base}.csv"
        data_df.to_csv(filepath, index=False)

        logger.info("Saved %d records to %s", len(data), filepath)
        return filepath
