"""
Centralized logging configuration for KavziTrader.

This module provides functions to set up logging across the application.
"""

import logging
import logging.handlers
import os
import sys


def setup_logging(
    log_level: str = "DEBUG",
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

    # Define formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d - %(message)s",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.info(f"Logging initialized with level {log_level}")

    # If dotenv is installed, log environment variables (except sensitive ones)
    try:
        from dotenv import load_dotenv

        load_dotenv()
        logger.debug("Environment variables loaded from .env file")

        # Log non-sensitive environment variables at debug level
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
            logger.debug(f"Relevant environment variables: {env_vars}")

    except ImportError:
        logger.debug(
            "python-dotenv not installed. Environment variables must be set manually.",
        )

    return logger
