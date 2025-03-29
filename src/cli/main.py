"""
KavziTrader - Neural Network-Based Crypto Trading Platform.

This module serves as the main entry point for the KavziTrader CLI.
"""

import sys
from pathlib import Path

import click

# Add src to path to allow imports from src package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Setup logging
from src.commons.logging import setup_logging

# Initialize logger
logger = setup_logging(name="kavzitrader")


@click.group()
@click.version_option()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file",
)
def cli(verbose: bool, config: str | None) -> None:
    """KavziTrader - Neural Network-Based Crypto Trading Platform."""
    if verbose:
        # Update the log level if verbose mode is enabled
        logger.setLevel("DEBUG")
        logger.debug("Verbose mode enabled")

    if config:
        logger.info(f"Using configuration file: {config}")

    from dotenv import load_dotenv

    load_dotenv()  # take environment variables


@cli.group()
def data() -> None:
    """Data management commands."""


@data.command("fetch")
@click.option("--symbol", required=True, help="Trading pair symbol")
@click.option("--interval", default="1h", help="Timeframe (1m, 5m, 1h, etc.)")
@click.option("--start-date", help="Start date for historical data (YYYY-MM-DD)")
@click.option("--end-date", help="End date for historical data (YYYY-MM-DD)")
@click.option("--limit", type=int, help="Maximum number of candles")
def fetch_data(
    symbol: str,
    interval: str,
    start_date: str | None,
    end_date: str | None,
    limit: int | None,
) -> None:
    """
    Fetch historical market data from Binance.

    Args:
        symbol: Trading pair symbol
        interval: Timeframe (1m, 5m, 1h, etc.)
        start_date: Start date for historical data (YYYY-MM-DD)
        end_date: End date for historical data (YYYY-MM-DD)
        limit: Maximum number of candles
    """
    click.echo(f"Fetching {symbol} data with {interval} interval")
    click.echo(f"Start date: {start_date}")
    click.echo(f"End date: {end_date}")
    click.echo(f"Limit: {limit}")
    # Implementation will be added later


@cli.group()
def model() -> None:
    """Model management commands."""


@model.command("train")
@click.option("--config-name", required=True, help="Model configuration name")
@click.option("--symbol", required=True, help="Trading pair to train on")
def train_model(config_name: str, symbol: str) -> None:
    """
    Train a model with the specified configuration.

    Args:
        config_name: Model configuration name
        symbol: Trading pair to train on
    """
    click.echo(f"Training model {config_name} for {symbol}")
    # Implementation will be added later


@cli.group()
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
def run_backtest(plan: str, start_date: str | None, end_date: str | None) -> None:
    """
    Run a backtest with the specified trading plan.

    Args:
        plan: Trading plan file
        start_date: Backtest start date (YYYY-MM-DD)
        end_date: Backtest end date (YYYY-MM-DD)
    """
    click.echo(f"Running backtest with plan {plan}")
    click.echo(f"Start date: {start_date}")
    click.echo(f"End date: {end_date}")
    # Implementation will be added later


@cli.group()
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
def paper_trade(plan: str, capital: float) -> None:
    """
    Run paper trading with the specified trading plan.

    Args:
        plan: Trading plan file
        capital: Initial capital
    """
    click.echo(f"Starting paper trading with plan {plan} and capital {capital}")
    # Implementation will be added later


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
def live_trade(plan: str, check_balance: bool) -> None:
    """
    Run live trading with the specified trading plan.

    Args:
        plan: Trading plan file
        check_balance: Verify account balance before trading
    """
    click.echo(f"Starting live trading with plan {plan}")
    click.echo(f"Check balance: {check_balance}")
    # Implementation will be added later


@cli.group()
def system() -> None:
    """System management commands."""


@system.command("setup")
@click.option("--database", is_flag=True, help="Initialize database")
@click.option("--force", is_flag=True, help="Force setup (overwrite)")
def setup_system(database: bool, force: bool) -> None:
    """
    Set up system components.

    Args:
        database: Initialize database
        force: Force setup (overwrite)
    """
    if database:
        click.echo("Initializing database")
        click.echo(f"Force: {force}")
        # Implementation will be added later


if __name__ == "__main__":
    cli()
