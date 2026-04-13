"""
Tests for time utility functions.
"""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from kavzi_trader.commons.time_utility import (
    MILLISECONDS_IN_SECOND,
    date_to_milliseconds,
    milliseconds_to_datetime,
    normalize_datetime_to_utc,
    timestamp_filename,
    timestamp_path,
    utc_now,
    utc_timestamp,
)


def test_utc_now() -> None:
    """Test that utc_now returns a datetime with UTC timezone."""
    dt = utc_now()
    assert isinstance(dt, datetime)
    assert dt.tzinfo == UTC


def test_utc_timestamp() -> None:
    """Test conversion of timestamp to UTC datetime."""
    dt = utc_timestamp(1609459200.0)  # 2021-01-01
    assert isinstance(dt, datetime)
    assert dt.year == 2021
    assert dt.month == 1
    assert dt.day == 1
    assert dt.tzinfo == UTC


def test_timestamp_filename() -> None:
    """Test generation of timestamped filename."""
    filename = timestamp_filename("test", "csv")
    assert isinstance(filename, str)
    assert filename.startswith("test_")
    assert filename.endswith(".csv")

    # Default extension
    filename = timestamp_filename("test")
    assert filename.endswith(".json")


def test_timestamp_path(tmp_path: Path) -> None:
    """Test generation of timestamped path."""
    path = timestamp_path("test", tmp_path, "csv")
    assert str(path).startswith(str(tmp_path))
    assert path.name.startswith("test_")
    assert path.suffix == ".csv"


def test_date_to_milliseconds() -> None:
    """Test conversion of date string to milliseconds."""
    ms = date_to_milliseconds("2021-01-01")
    assert isinstance(ms, int)

    # Convert back to date for verification
    dt = utc_timestamp(ms / MILLISECONDS_IN_SECOND)
    assert dt.year == 2021
    assert dt.month == 1
    assert dt.day == 1


def test_date_to_milliseconds_with_invalid_input() -> None:
    """Test conversion of invalid date string raises error."""
    with pytest.raises(ValueError):
        date_to_milliseconds("not a date")


def test_milliseconds_to_datetime() -> None:
    """Test conversion of milliseconds to datetime."""
    dt = milliseconds_to_datetime(1609459200000)  # 2021-01-01
    assert isinstance(dt, datetime)
    assert dt.year == 2021
    assert dt.month == 1
    assert dt.day == 1
    assert dt.tzinfo == UTC


def test_normalize_datetime_to_utc_naive_is_tagged_utc() -> None:
    """Naive datetimes are assumed to represent UTC and get tagged as such."""
    naive = datetime(2024, 6, 1, 12, 30)  # noqa: DTZ001
    assert naive.tzinfo is None

    result = normalize_datetime_to_utc(naive)

    assert result.tzinfo == UTC
    assert result.year == 2024
    assert result.hour == 12


def test_normalize_datetime_to_utc_aware_non_utc_is_converted() -> None:
    """Aware datetimes in other zones are converted to UTC."""
    plus_three = timezone(timedelta(hours=3))
    aware = datetime(2024, 6, 1, 15, 30, tzinfo=plus_three)

    result = normalize_datetime_to_utc(aware)

    assert result.tzinfo == UTC
    assert result.hour == 12  # 15:30 +03:00 → 12:30 UTC


def test_normalize_datetime_to_utc_preserves_utc_aware() -> None:
    """UTC-aware datetimes pass through unchanged."""
    aware = datetime(2024, 6, 1, 12, 30, tzinfo=UTC)

    result = normalize_datetime_to_utc(aware)

    assert result == aware
    assert result.tzinfo == UTC
