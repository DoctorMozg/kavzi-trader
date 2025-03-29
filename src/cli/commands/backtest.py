"""
Backtesting commands for the KavziTrader CLI.
"""

import click

from src.commons.logging import get_logger

# Initialize logger
logger = get_logger(name="kavzitrader.cli.backtest")


@click.group()
def backtest() -> None:
    """Backtesting commands."""


@backtest.command("run")
@click.option(
    "--plan",
    required=True,
    type=click.Path(exists=True),
    help="Trading plan file",
)
@click.option("--start-date", help="Backtest start date (YYYY-MM-DD)")
@click.option("--end-date", help="Backtest end date (YYYY-MM-DD)")
@click.pass_context
def run_backtest(
    plan: str,
    start_date: str | None,
    end_date: str | None,
) -> None:
    """
    Run a backtest with the specified trading plan.

    Args:
        plan: Trading plan file path
        start_date: Backtest start date (YYYY-MM-DD)
        end_date: Backtest end date (YYYY-MM-DD)
    """
    click.echo(f"Running backtest with plan: {plan}")
    click.echo(f"Start date: {start_date}")
    click.echo(f"End date: {end_date}")
