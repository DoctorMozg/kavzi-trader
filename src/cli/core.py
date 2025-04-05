"""
Core functionality for the KavziTrader CLI.

This module contains the core functionality for the KavziTrader CLI,
including the HydraOptionsGroup class for handling Hydra configuration overrides.
"""

import logging
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

# Add src to path to allow imports from src package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import AppConfig
from src.data.storage.database_async import AsyncDatabase

# Initialize logger
logger = logging.getLogger(__name__)


def setup_cli_environment(
    ctx: click.Context,
    verbose: bool,
) -> None:
    """
    Set up the CLI environment with configuration and logging.

    Args:
        ctx: Click context
        verbose: Whether to enable verbose output
    """
    # Load environment variables
    load_dotenv()

    # Create app config from environment variables
    app_config = AppConfig.from_env()

    # Set up logging
    log_level = "DEBUG" if verbose else app_config.system.log_level
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.setLevel(log_level)

    if verbose:
        logger.debug("Verbose mode enabled")

    # Initialize database connection
    try:
        db = AsyncDatabase(app_config.database.url)

        # Store in context for child commands
        ctx.obj = ctx.obj or {}
        ctx.obj.update(
            {
                "app_config": app_config,
                "db": db,
            },
        )

        logger.info("Configuration loaded successfully")

    except Exception:
        logger.exception("Error initializing application")
        ctx.fail("Failed to initialize application")
