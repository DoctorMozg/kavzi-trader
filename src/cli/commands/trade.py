"""
Trading commands for the KavziTrader CLI.
"""

import logging

import click

# Initialize logger
logger = logging.getLogger(__name__)


@click.group()
def trade() -> None:
    """Trading commands."""


@trade.command("paper")
@click.option(
    "--plan",
    required=True,
    type=click.Path(exists=True),
    help="Trading plan file",
)
@click.option("--capital", type=float, default=10000.0, help="Initial capital")
@click.pass_context
def paper_trade(plan: str, capital: float) -> None:
    """
    Run paper trading with the specified trading plan.

    Args:
        plan: Trading plan file path
        capital: Initial capital
    """
    click.echo(f"Starting paper trading with plan: {plan}")
    click.echo(f"Initial capital: ${capital}")


@trade.command("live")
@click.option(
    "--plan",
    required=True,
    type=click.Path(exists=True),
    help="Trading plan file",
)
@click.option(
    "--check-balance",
    is_flag=True,
    help="Verify account balance before trading",
)
@click.pass_context
def live_trade(plan: str, check_balance: bool) -> None:
    """
    Run live trading with the specified trading plan.

    Args:
        plan: Trading plan file path
        check_balance: Whether to verify account balance
    """
    click.echo(f"Starting LIVE TRADING with plan: {plan}")
    click.echo(f"Check balance: {check_balance}")
