"""
Path utility functions for KavziTrader.

This module provides common path-related utility functions used across
the KavziTrader platform, ensuring consistent path handling.
"""

from pathlib import Path


def ensure_directory_exists(path: Path) -> Path:
    """
    Ensure that a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists

    Returns:
        Path: The same path that was passed in
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
