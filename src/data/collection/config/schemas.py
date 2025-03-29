"""
Configuration schemas for historical data collection.

This module defines Pydantic schemas for configuring the historical data
collection process, including fetch parameters, validation settings, and
storage options.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from src.api.binance.constants import KLINE_INTERVALS
from src.commons.datetime_schema import DateTimeWithTimezoneSchema
from src.commons.time_utility import utc_now


class HistoricalDataFetchConfigSchema(BaseModel):
    """Configuration for historical data fetching."""

    symbol: str = Field(..., description="Trading pair symbol (e.g., 'BTCUSDT')")
    interval: str = Field(..., description="Timeframe interval (e.g., '1m', '1h')")
    start_time: datetime = Field(..., description="Start time for data collection")
    end_time: Optional[datetime] = Field(
        None, description="End time for data collection (defaults to now)"
    )
    batch_size: int = Field(1000, description="Number of candles per batch", gt=0)
    max_workers: int = Field(4, description="Maximum number of parallel workers", gt=0)
    force_full: bool = Field(
        False, description="Force full download instead of incremental"
    )
    validate: bool = Field(True, description="Validate data during collection")
    store_csv: bool = Field(
        False, description="Also store data as CSV files in addition to database"
    )
    output_dir: Optional[Path] = Field(
        None, description="Output directory for CSV files (if store_csv is True)"
    )

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: str) -> str:
        """Validate that the interval is supported by Binance."""
        if v not in KLINE_INTERVALS:
            valid_intervals = ", ".join(KLINE_INTERVALS.keys())
            raise ValueError(
                f"Invalid interval: {v}. Valid intervals are: {valid_intervals}"
            )
        return v

    @field_validator("end_time", mode="before")
    @classmethod
    def set_default_end_time(cls, v: Optional[datetime]) -> datetime:
        """Set default end time to now if not provided."""
        if v is None:
            return utc_now()
        return v


class DataValidationConfigSchema(BaseModel):
    """Configuration for data validation."""

    max_gap_percent: float = Field(
        2.0, description="Maximum allowed gap between candles in percent of interval"
    )
    check_sequence: bool = Field(
        True, description="Check for sequence continuity in timestamps"
    )
    check_outliers: bool = Field(True, description="Check for price/volume outliers")
    outlier_std_threshold: float = Field(
        3.0, description="Standard deviation threshold for outlier detection"
    )
    min_volume: float = Field(
        0.0, description="Minimum allowed volume (0 means no minimum)"
    )


class IncrementalUpdateConfigSchema(BaseModel):
    """Configuration for incremental updates."""

    check_gaps: bool = Field(
        True, description="Check for and fill gaps in historical data"
    )
    look_back_periods: int = Field(
        5,
        description="Number of periods to look back when checking for data consistency",
    )
    auto_fill_gaps: bool = Field(
        True, description="Automatically fill detected gaps in data"
    )
    retry_attempts: int = Field(
        3, description="Number of retry attempts for failed data fetches"
    )
    retry_delay_seconds: int = Field(
        10, description="Delay between retry attempts in seconds"
    )


class HistoricalDataCollectionConfigSchema(BaseModel):
    """Main configuration for historical data collection."""

    fetch: HistoricalDataFetchConfigSchema
    validation: DataValidationConfigSchema = Field(default_factory=DataValidationConfigSchema)
    incremental: IncrementalUpdateConfigSchema = Field(
        default_factory=IncrementalUpdateConfigSchema
    ) 