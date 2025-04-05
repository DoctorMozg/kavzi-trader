"""
KavziTrader - Neural Network-Based Crypto Trading Platform.

This module serves as the main entry point for the KavziTrader CLI.
"""

import logging
import sys
from pathlib import Path

import click

# Add src to path to allow imports from src package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Import core CLI functionality
from kavzi_trader.cli.commands.backtest import backtest
from kavzi_trader.cli.commands.config import config_command

# Import command groups
from kavzi_trader.cli.commands.data import data
from kavzi_trader.cli.commands.model import model
from kavzi_trader.cli.commands.system import system
from kavzi_trader.cli.commands.trade import trade
from kavzi_trader.cli.core import setup_cli_environment

# Initialize logger
logger = logging.getLogger(__name__)


@click.group()
@click.version_option()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
) -> None:
    """
    KavziTrader - Neural Network-Based Crypto Trading Platform.

    You can pass hydra configuration overrides as key=value pairs after the command.
    """
    # Set up the CLI environment
    setup_cli_environment(ctx, verbose)


# Register command groups
cli.add_command(data)
cli.add_command(model)
cli.add_command(backtest)
cli.add_command(trade)
cli.add_command(system)
cli.add_command(config_command)


if __name__ == "__main__":
    cli(obj={})  # pylint: disable=no-value-for-parameter
