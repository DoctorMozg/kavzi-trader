"""
Time utility functions for KavziTrader.

This module provides common time-related utility functions used across
the KavziTrader platform, ensuring consistent timestamp handling.
"""

from datetime import UTC, datetime
from pathlib import Path


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
