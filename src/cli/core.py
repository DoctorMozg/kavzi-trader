"""
Core functionality for the KavziTrader CLI.

This module contains the core functionality for the KavziTrader CLI,
including the HydraOptionsGroup class for handling Hydra configuration overrides.
"""

import sys
from pathlib import Path

import click

# Add src to path to allow imports from src package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Setup logging
from src.commons.logging import get_logger
from src.config.hydra_util import (
    config_to_app_config,
    get_config,
    init_hydra,
    resolve_relative_paths,
)

# Initialize logger
logger = get_logger(name="kavzitrader.cli")

# Initialize Hydra
init_hydra()


class HydraOptionsGroup(click.Group):
    """Custom Group class that captures all unparsed options as Hydra overrides."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Parse arguments and capture unparsed ones for Hydra."""
        # First, let the base class parse the standard options
        parsed_args: list[str] = super().parse_args(ctx, args)

        # Extract any remaining arguments which will be passed to Hydra
        # Format of code: key=value
        hydra_overrides: list[str] = [
            arg for arg in args if "=" in arg and not arg.startswith(("-", "--"))
        ]

        # Store the overrides in the context
        ctx.obj = ctx.obj or {}
        ctx.obj["hydra_overrides"] = hydra_overrides

        return parsed_args


def setup_cli_environment(
    ctx: click.Context,
    verbose: bool,
    config: str | None,
    config_dir: str | None,
    config_name: str | None,
) -> None:
    """
    Set up the CLI environment with configuration and logging.

    Args:
        ctx: Click context
        verbose: Whether to enable verbose output
        config: Path to configuration file
        config_dir: Path to configuration directory
        config_name: Name of the configuration to use
    """
    if verbose:
        # Update the log level if verbose mode is enabled
        logger.setLevel("DEBUG")
        logger.debug("Verbose mode enabled")

    # Load environment variables
    from dotenv import load_dotenv

    load_dotenv()  # take environment variables

    # Get Hydra overrides from context
    hydra_overrides = ctx.obj.get("hydra_overrides", []) if ctx.obj else []

    if hydra_overrides:
        logger.debug(f"Hydra overrides from command line: {hydra_overrides}")

    # Prepare Hydra config overrides from config file if specified
    if config:
        logger.info(f"Using configuration file: {config}")
        # We'll handle this custom config file differently
        # by loading it directly instead of through Hydra

    # Load the configuration
    try:
        # Get Hydra configuration
        hydra_config = get_config(
            config_path=config_dir,
            config_name=config_name,
            overrides=hydra_overrides,
        )

        # Resolve relative paths
        hydra_config = resolve_relative_paths(hydra_config)
        # Convert to AppConfig for type safety
        app_config = config_to_app_config(hydra_config)

        # Store in context for child commands
        ctx.obj = ctx.obj or {}
        ctx.obj.update(
            {
                "config": hydra_config,  # Original Hydra config
                "app_config": app_config,  # Pydantic validated config
            },
        )

        logger.info("Configuration loaded successfully")

    except Exception:
        logger.exception("Error loading configuration")
        ctx.fail("Failed to load configuration")
