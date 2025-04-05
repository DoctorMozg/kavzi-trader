"""
Path utility functions for KavziTrader.

This module provides common path-related utility functions used across
the KavziTrader platform, ensuring consistent path handling.
"""

import logging
from pathlib import Path

# Initialize logger
logger = logging.getLogger(__name__)


def create_output_path(
    output_dir: str | None = None,
    default_dir: str = "./data",
) -> Path:
    """
    Create an output directory path.

    Args:
        output_dir: Optional output directory string
        default_dir: Default directory to use if output_dir is None

    Returns:
        Path: Output directory path
    """
    path = Path(output_dir) if output_dir else Path(default_dir)
    logger.debug("Using output path: %s", path)
    return path


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
