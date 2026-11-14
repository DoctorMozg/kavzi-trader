"""
KavziTrader - LLM-Based Crypto Futures Trading Platform.

This module serves as the main entry point for the KavziTrader CLI.
"""

import click
import pydantic_ai

from kavzi_trader.cli.commands.config import config_command
from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.cli.commands.model import model
from kavzi_trader.cli.commands.trade import trade
from kavzi_trader.cli.commands.ui import ui
from kavzi_trader.cli.core import setup_cli_environment


@click.group()
@click.version_option()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
) -> None:
    """
    KavziTrader - LLM-Based Crypto Futures Trading Platform.
    """
    # Stdout carries structured logs; suppress pydantic-ai's first-run banner.
    pydantic_ai.BANNER_ENABLED = False
    setup_cli_environment(ctx, verbose)


# Register command groups
cli.add_command(model)
cli.add_command(trade)
cli.add_command(config_command)
cli.add_command(ui)
cli.add_command(eval_group)


if __name__ == "__main__":
    cli(obj={})  # pylint: disable=no-value-for-parameter
