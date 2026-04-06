"""
Time utility functions for KavziTrader.

This module provides common time-related utility functions used across
the KavziTrader platform, ensuring consistent timestamp handling.
"""

from datetime import UTC, datetime
from pathlib import Path

import dateparser

MILLISECONDS_IN_SECOND = 1000


def utc_now() -> datetime:
    """
    Get the current UTC timestamp with timezone information.

    Returns:
        Current datetime in UTC with timezone set to UTC

    Example:
        >>> ts = now_ts()
        >>> ts.tzinfo
        UTC
    """
    return datetime.now(UTC)


def utc_timestamp(time: float) -> datetime:
    """
    Convert a timestamp in milliseconds to a datetime object in UTC.

    Args:
        time: Timestamp in milliseconds
    """

    return datetime.fromtimestamp(time, UTC)


def timestamp_filename(prefix: str, extension: str = "json") -> str:
    """
    Generate a filename with the current timestamp.

    Args:
        prefix: Prefix for the filename
        extension: File extension (without the dot)

    Returns:
        Filename string with format: prefix_YYYYMMDD_HHMMSS.extension

    Example:
        >>> timestamp_filename("model", "pt")
        'model_20230615_123045.pt'
    """
    ts = utc_now()
    timestamp_str = ts.strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp_str}.{extension}"


def timestamp_path(prefix: str, directory: Path, extension: str = "json") -> Path:
    """
    Generate a full path with a timestamped filename.

    Args:
        prefix: Prefix for the filename
        directory: Directory to place the file in
        extension: File extension (without the dot)

    Returns:
        Path object with a timestamped filename

    Example:
        >>> timestamp_path("model", Path("/tmp"), "pt")
        PosixPath('/tmp/model_20230615_123045.pt')
    """
    filename = timestamp_filename(prefix, extension)
    return directory / filename


def date_to_milliseconds(date_str: str) -> int:
    """
    Convert a date string to milliseconds.

    Args:
        date_str: Date string in readable format,
            e.g., "1 Jan, 2020", "1 hour ago UTC"

    Returns:
        Milliseconds since epoch
    """
    return int(parse_date_string(date_str).timestamp() * MILLISECONDS_IN_SECOND)


def milliseconds_to_datetime(milliseconds: int) -> datetime:
    """
    Convert milliseconds to datetime.

    Args:
        milliseconds: Milliseconds since epoch

    Returns:
        Datetime object
    """
    return utc_timestamp(milliseconds / MILLISECONDS_IN_SECOND)


def parse_date_string(date_str: str) -> datetime:
    """
    Parse a date string into a datetime object with UTC timezone.

    This function handles various date formats and ensures the result
    has proper timezone information.

    Args:
        date_str: Date string in various formats (e.g., YYYY-MM-DD,
                 YYYY-MM-DD HH:MM:SS, "1 day ago", etc.)

    Returns:
        datetime: Parsed datetime object with UTC timezone

    Raises:
        ValueError: If the date string cannot be parsed
    """
    parsed_date = dateparser.parse(
        date_str,
        settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True},
    )
    if not parsed_date:
        raise ValueError(f"Could not parse date: {date_str}")
    return parsed_date
