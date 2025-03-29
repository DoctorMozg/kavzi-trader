"""
Data management commands for the KavziTrader CLI.
"""

import click

from src.commons.logging import get_logger

# Initialize logger
logger = get_logger(name="kavzitrader.cli.data")


@click.group()
def data() -> None:
    """Data management commands."""


@data.command("fetch")
@click.option("--symbol", required=True, help="Trading pair symbol")
@click.option("--interval", default="1h", help="Timeframe (1m, 5m, 1h, etc.)")
@click.option("--start-date", help="Start date for historical data (YYYY-MM-DD)")
@click.option("--end-date", help="End date for historical data (YYYY-MM-DD)")
@click.option("--limit", type=int, help="Maximum number of candles")
@click.pass_context
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

    # Note: Consider redirecting users to the more
    # full-featured historical fetch command
    click.echo(
        "\nTip: For more options, try 'kavzitrader data historical fetch' instead.",
    )
