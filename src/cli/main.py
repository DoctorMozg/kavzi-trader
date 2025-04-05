"""
KavziTrader - Neural Network-Based Crypto Trading Platform.

This module serves as the main entry point for the KavziTrader CLI.
"""

import sys
from pathlib import Path

import click

# Add src to path to allow imports from src package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Import core CLI functionality
from src.cli.commands.backtest import backtest
from src.cli.commands.config import config_command

# Import command groups
from src.cli.commands.data import data
from src.cli.commands.model import model
from src.cli.commands.system import system
from src.cli.commands.trade import trade
from src.cli.core import HydraOptionsGroup, setup_cli_environment

# Setup logging
from src.commons.logging import setup_logging

# Initialize logger
logger = setup_logging(
    name="kavzitrader",
)


@click.group(cls=HydraOptionsGroup)
@click.version_option()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file",
)
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to configuration directory",
)
@click.option(
    "--config-name",
    help="Name of the configuration to use (without extension)",
)
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
    config: str | None,
    config_dir: str | None,
    config_name: str | None,
) -> None:
    """
    KavziTrader - Neural Network-Based Crypto Trading Platform.

    You can pass hydra configuration overrides as key=value pairs after the command.
    """
    # Set up the CLI environment
    setup_cli_environment(ctx, verbose, config, config_dir, config_name)


# Register command groups
cli.add_command(data)
cli.add_command(model)
cli.add_command(backtest)
cli.add_command(trade)
cli.add_command(system)
cli.add_command(config_command)


if __name__ == "__main__":
    cli(obj={})  # pylint: disable=no-value-for-parameter
