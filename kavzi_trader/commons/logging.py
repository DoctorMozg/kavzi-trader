"""
Centralized logging configuration for KavziTrader.

This module provides functions to set up logging across the application.
"""

import logging
import os
import sys
from pathlib import Path

from kavzi_trader.commons.time_utility import timestamp_path
from kavzi_trader.monitoring.structured_logger import JsonLogFormatter

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    _load_dotenv = None


def setup_logging(
    log_level: str = "DEBUG",
    name: str = "kavzi_trader",
    log_dir: Path | None = None,
    log_format: str = "text",
    console: bool = True,
) -> logging.Logger:
    """
    Set up logging for the application.

    Args:
        config: Application configuration (optional)
        log_level: Log level override (optional)
        log_file: Log file path (optional)
        console: Whether to log to console
        name: Logger name

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        logger.handlers.clear()

    # Determine log level
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level = level_map.get(log_level, logging.DEBUG)
    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d - %(message)s",
    )
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = timestamp_path("kavzitrader_log", log_dir, extension="jsonl")
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        if log_format == "json":
            file_handler.setFormatter(JsonLogFormatter())
        else:
            file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.info("Logging initialized with level %s", log_level)

    if _load_dotenv is not None:
        _load_dotenv()
        logger.debug("Environment variables loaded from .env file")

        excluded_vars = {
            "BINANCE_API_KEY",
            "BINANCE_API_SECRET",
            "SECRET_KEY",
        }
        env_vars = {
            k: "***" if k in excluded_vars else v
            for k, v in os.environ.items()
            if k.startswith(("BINANCE_", "APP_", "LOG_", "DB_"))
        }

        if env_vars:
            logger.debug("Relevant environment variables: %s", env_vars)
    else:
        logger.debug(
            "python-dotenv not installed. Environment variables must be set manually.",
        )

    return logger
