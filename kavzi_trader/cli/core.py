"""
Core functionality for the KavziTrader CLI.
"""

import logging
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from kavzi_trader.config import AppConfig

logger = logging.getLogger(__name__)


def setup_cli_environment(
    ctx: click.Context,
    verbose: bool,
) -> None:
    load_dotenv()

    app_config = AppConfig.from_env()

    log_level = "DEBUG" if verbose else app_config.system.log_level
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.setLevel(log_level)

    if verbose:
        logger.debug("Verbose mode enabled")

    ctx.obj = ctx.obj or {}
    ctx.obj["app_config"] = app_config

    logger.info("Configuration loaded successfully")
