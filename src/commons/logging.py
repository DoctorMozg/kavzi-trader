"""
Centralized logging configuration for KavziTrader.

This module provides functions to set up logging across the application.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from src.config import AppConfig


def setup_logging(
    config: AppConfig | None = None,
    log_level: str | None = None,
    log_file: str | Path | None = None,
    console: bool = True,
    name: str = "kavzitrader",
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
    # Get the root logger
    logger = logging.getLogger(name)

    # Clear any existing handlers to avoid duplicate logging
    if logger.handlers:
        logger.handlers.clear()

    # Determine log level
    level_str = log_level or (config.system.log_level if config else "INFO")
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level = level_map.get(level_str, logging.DEBUG)
    logger.setLevel(level)

    # Define formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d - %(message)s",
    )

    # Add console handler if requested
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Add file handler if log file is specified
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # If config is provided and log_file wasn't specified, check for data_dir/logs
    elif config and not log_file:
        log_dir = Path(config.system.data_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{name}.log"

        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.info(f"Logging initialized with level {level_str}")

    # If dotenv is installed, log environment variables (except sensitive ones)
    try:
        from dotenv import load_dotenv

        load_dotenv()
        logger.debug("Environment variables loaded from .env file")

        # Log non-sensitive environment variables at debug level
        excluded_vars = {
            "BINANCE_API_KEY",
            "BINANCE_API_SECRET",
            "DB_PASSWORD",
            "SECRET_KEY",
        }
        env_vars = {
            k: "***" if k in excluded_vars else v
            for k, v in os.environ.items()
            if k.startswith(("BINANCE_", "APP_", "LOG_", "DB_"))
        }

        if env_vars:
            logger.debug(f"Relevant environment variables: {env_vars}")

    except ImportError:
        logger.debug(
            "python-dotenv not installed. Environment variables must be set manually.",
        )

    return logger


def get_logger(name: str = "kavzitrader") -> logging.Logger:
    """
    Get a logger with the given name.

    This is a convenience function to get a logger that inherits from the root logger.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
