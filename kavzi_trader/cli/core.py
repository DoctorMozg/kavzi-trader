"""
Core functionality for the KavziTrader CLI.
"""

import logging

import click
from dotenv import load_dotenv

from kavzi_trader.commons.logging import setup_logging
from kavzi_trader.config import AppConfig

logger = logging.getLogger(__name__)


def setup_cli_environment(
    ctx: click.Context,
    verbose: bool,
) -> None:
    load_dotenv()

    app_config = AppConfig.from_env()

    log_level = "DEBUG" if verbose else app_config.monitoring.log_level
    setup_logging(
        log_level=log_level,
        log_dir=app_config.system.results_dir / "logs",
        log_format=app_config.monitoring.log_format,
        console=True,
        name="kavzi_trader",
    )

    if verbose:
        logger.debug("Verbose mode enabled")

    ctx.obj = ctx.obj or {}
    ctx.obj["app_config"] = app_config

    logger.info("Configuration loaded successfully")
