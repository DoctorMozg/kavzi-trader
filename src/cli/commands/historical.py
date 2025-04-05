"""
Historical data collection commands for the KavziTrader CLI.

This module provides commands for downloading historical market data from Binance,
with support for different data types, timeframes, and filtering options.
"""

from datetime import timedelta

import click

from src.api.binance.historical.batch import (
    DownloadBatchConfigSchema,
    SymbolicDownloadBatchConfigSchema,
)
from src.api.binance.historical.client import BinanceHistoricalDataClient
from src.commons.async_utils import to_sync
from src.commons.logging import get_logger
from src.commons.time_utility import parse_date_range, utc_now
from src.config import AppConfig
from src.data.storage.database_async import AsyncDatabase
from src.logic.historical.download_service import HistoricalDownloadService

# Initialize logger
logger = get_logger(name=__name__)


@click.group()
def historical() -> None:
    """Historical data collection commands."""


@historical.command("fetch")
@click.option("--symbol", required=True, help="Trading pair symbol (e.g., BTCUSDT)")
@click.option(
    "--interval",
    default="1h",
    help="Kline interval (e.g., 1m, 5m, 15m, 1h, 4h, 1d)",
)
@click.option(
    "--start-date",
    required=True,
    help="Start date for historical data (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
)
@click.option(
    "--end-date",
    help="End date for historical data (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
)
@click.option(
    "--batch-size",
    type=int,
    default=1000,
    help="Size of each download batch",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="Maximum number of concurrent download workers",
)
@click.pass_context
@to_sync
async def fetch_historical(
    ctx: click.Context,
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str | None,
    batch_size: int,
    max_workers: int,
) -> None:
    """
    Fetch historical klines (candlestick) data from Binance.

    This command downloads historical klines data for a specific symbol and interval,
    with support for batching and parallel downloads.

    Examples:
        kavzitrader data historical fetch --symbol BTCUSDT --interval 1h \
            --start-date "2023-01-01"
        kavzitrader data historical fetch --symbol ETHUSDT --interval 15m \
            --start-date "2023-01-01" --end-date "2023-01-31"
    """
    # Get configuration
    app_config: AppConfig = ctx.obj["app_config"]

    # Parse dates
    start_time, end_time = parse_date_range(start_date, end_date)

    # Get API credentials from config
    api_key = app_config.api.binance.api_key
    api_secret = app_config.api.binance.api_secret

    # Initialize client
    client = BinanceHistoricalDataClient(
        api_key=api_key,
        api_secret=api_secret,
        max_workers=max_workers,
        batch_size=batch_size,
    )

    # Get database from context
    db: AsyncDatabase = ctx.obj["db"]

    async with db.session_scope() as db_session:
        service = HistoricalDownloadService(client, db_session)

        try:
            # Create download config
            config = SymbolicDownloadBatchConfigSchema(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time or utc_now(),  # Provide a default value if None
                batch_size=batch_size,
                max_workers=max_workers,
            )

            # Download data
            data = await service.download_klines(config=config)

            # Report results
            click.echo(
                f"Successfully downloaded {len(data)} records for {symbol} {interval}",
            )
            click.echo("Data saved to database")

        except Exception as e:
            logger.exception("Error downloading historical data")
            raise click.ClickException(f"Failed to download data: {e!s}") from e


@historical.command("fetch-trades")
@click.option("--symbol", required=True, help="Trading pair symbol (e.g., BTCUSDT)")
@click.option(
    "--start-date",
    required=True,
    help="Start date for historical data (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
)
@click.option(
    "--end-date",
    help="End date for historical data (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="Maximum number of concurrent download workers",
)
@click.pass_context
@to_sync
async def fetch_trades(
    ctx: click.Context,
    symbol: str,
    start_date: str,
    end_date: str | None,
    max_workers: int,
) -> None:
    """
    Fetch historical trades data from Binance.

    This command downloads historical trades data for a specific symbol,
    with support for parallel downloads.

    Examples:
        kavzitrader data historical fetch-trades --symbol BTCUSDT \
            --start-date "2023-01-01"
        kavzitrader data historical fetch-trades --symbol ETHUSDT \
            --start-date "2023-01-01" --end-date "2023-01-02"
    """
    # Get configuration
    app_config: AppConfig = ctx.obj["app_config"]

    # Parse dates
    start_time, end_time = parse_date_range(start_date, end_date)

    # Get API credentials from config
    api_key = app_config.api.binance.api_key
    api_secret = app_config.api.binance.api_secret

    # Initialize client
    client = BinanceHistoricalDataClient(
        api_key=api_key,
        api_secret=api_secret,
        max_workers=max_workers,
        batch_size=1000,  # Default batch size
    )

    # Get database from context
    db: AsyncDatabase = ctx.obj["db"]

    async with db.session_scope() as db_session:
        service = HistoricalDownloadService(client, db_session)

        try:
            # Create download config
            config = SymbolicDownloadBatchConfigSchema(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time or utc_now(),  # Provide a default value if None
                max_workers=max_workers,
            )

            # Download data
            data = await service.download_trades(config=config)

            # Report results
            click.echo(f"Successfully downloaded {len(data)} trades for {symbol}")
            click.echo("Data saved to database")

        except Exception as e:
            logger.exception("Error downloading trades data")
            raise click.ClickException(f"Failed to download trades: {e!s}") from e


@historical.command("fetch-multiple")
@click.option(
    "--symbols",
    required=True,
    help="Comma-separated list of trading pair symbols (e.g., BTCUSDT,ETHUSDT)",
)
@click.option(
    "--interval",
    default="1h",
    help="Kline interval (e.g., 1m, 5m, 15m, 1h, 4h, 1d)",
)
@click.option(
    "--start-date",
    required=True,
    help="Start date for historical data (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
)
@click.option(
    "--end-date",
    help="End date for historical data (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
)
@click.option(
    "--batch-size",
    type=int,
    default=1000,
    help="Size of each download batch",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="Maximum number of concurrent download workers",
)
@click.pass_context
@to_sync
async def fetch_multiple(
    ctx: click.Context,
    symbols: str,
    interval: str,
    start_date: str,
    end_date: str | None,
    batch_size: int,
    max_workers: int,
) -> None:
    """
    Fetch historical data for multiple symbols.

    This command downloads historical klines data for multiple symbols with the same
    configuration, processing each symbol sequentially.

    Examples:
        kavzitrader data historical fetch-multiple --symbols BTCUSDT,ETHUSDT,SOLUSDT \
            --interval 1h --start-date "2023-01-01"
    """
    # Get configuration
    app_config: AppConfig = ctx.obj["app_config"]

    # Parse symbols
    symbol_list = [s.strip() for s in symbols.split(",")]
    if not symbol_list:
        raise click.BadParameter("No symbols provided")

    # Parse dates
    start_time, end_time = parse_date_range(start_date, end_date)

    # Get API credentials from config
    api_key = app_config.api.binance.api_key
    api_secret = app_config.api.binance.api_secret

    # Initialize client
    client = BinanceHistoricalDataClient(
        api_key=api_key,
        api_secret=api_secret,
        max_workers=max_workers,
        batch_size=batch_size,
    )

    # Get database from context
    db: AsyncDatabase = ctx.obj["db"]

    async with db.session_scope() as db_session:
        service = HistoricalDownloadService(client, db_session)

        try:
            # Create download config
            base_config = DownloadBatchConfigSchema(
                interval=interval,
                start_time=start_time,
                end_time=end_time or utc_now(),  # Provide a default value if None
                batch_size=batch_size,
                max_workers=max_workers,
            )

            # Download data for multiple symbols
            results = await service.download_multiple_symbols(
                symbols=symbol_list,
                base_config=base_config,
            )

            # Report results
            successful = sum(1 for success in results.values() if success)
            click.echo(
                "Successfully downloaded data for "
                f"{successful}/{len(symbol_list)} symbols",
            )
            click.echo("Data saved to database")

        except Exception as e:
            logger.exception("Error downloading historical data")
            raise click.ClickException(f"Failed to download data: {e!s}") from e


@historical.command("fetch-all")
@click.option(
    "--interval",
    default="1h",
    help="Kline interval (e.g., 1m, 5m, 15m, 1h, 4h, 1d)",
)
@click.option(
    "--start-date",
    required=True,
    help="Start date for historical data (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
)
@click.option(
    "--end-date",
    help="End date for historical data (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
)
@click.option(
    "--quote-asset",
    default="USDT",
    help="Filter symbols by quote asset (e.g., USDT, BTC)",
)
@click.option(
    "--min-volume",
    type=float,
    help="Minimum 24h volume in USD",
)
@click.option(
    "--batch-size",
    type=int,
    default=1000,
    help="Size of each download batch",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="Maximum number of concurrent download workers",
)
@click.pass_context
@to_sync
async def fetch_all(
    ctx: click.Context,
    interval: str,
    start_date: str,
    end_date: str | None,
    quote_asset: str,
    min_volume: float | None,
    batch_size: int,
    max_workers: int,
) -> None:
    """
    Fetch historical data for all available symbols matching criteria.

    This command downloads historical klines data for all available symbols
    that match the specified criteria, such as quote asset and minimum volume.

    Examples:
        kavzitrader data historical fetch-all --interval 1h --start-date "2023-01-01" \
            --quote-asset USDT --min-volume 1000000
    """
    # Get configuration
    app_config: AppConfig = ctx.obj["app_config"]

    # Parse dates
    start_time, end_time = parse_date_range(start_date, end_date)

    # Get API credentials from config
    api_key = app_config.api.binance.api_key
    api_secret = app_config.api.binance.api_secret

    # Initialize client
    client = BinanceHistoricalDataClient(
        api_key=api_key,
        api_secret=api_secret,
        max_workers=max_workers,
        batch_size=batch_size,
    )

    # Get database from context
    db: AsyncDatabase = ctx.obj["db"]

    async with db.session_scope() as db_session:
        service = HistoricalDownloadService(client, db_session)

        # Log the operation
        filter_desc = f"quote_asset={quote_asset}"
        if min_volume:
            filter_desc += f", min_volume={min_volume}"

        logger.info(
            "Downloading data for all symbols matching criteria (%s) with interval %s"
            " from %s to %s",
            filter_desc,
            interval,
            start_time,
            end_time or "now",
        )

        try:
            # Create download config
            base_config = DownloadBatchConfigSchema(
                interval=interval,
                start_time=start_time,
                end_time=end_time or utc_now(),  # Provide a default value if None
                batch_size=batch_size,
                max_workers=max_workers,
            )

            # Download data for all symbols
            results = await service.download_all_symbols(
                base_config=base_config,
                quote_asset=quote_asset,
                min_volume=min_volume,
            )

            # Report results
            successful = sum(1 for success in results.values() if success)
            click.echo(f"Successfully downloaded data for {successful} symbols")
            click.echo("Data saved to database")

        except Exception as e:
            logger.exception("Error downloading historical data")
            raise click.ClickException(f"Failed to download data: {e!s}") from e


@historical.command("update")
@click.option(
    "--symbol",
    help="Trading pair symbol (e.g., BTCUSDT)."
    " If not provided, updates all symbols in the database.",
)
@click.option(
    "--interval",
    default="1h",
    help="Kline interval (e.g., 1m, 5m, 15m, 1h, 4h, 1d)",
)
@click.option(
    "--days-back",
    type=int,
    default=1,
    help="Number of days to look back for existing data",
)
@click.option(
    "--batch-size",
    type=int,
    default=1000,
    help="Size of each download batch",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="Maximum number of concurrent download workers",
)
@click.pass_context
@to_sync
async def update_historical(
    ctx: click.Context,
    symbol: str | None,
    interval: str,
    days_back: int,
    batch_size: int,
    max_workers: int,
) -> None:
    """
    Update historical data with the latest available data.

    This command updates existing historical data by downloading only the new data
    since the last download. It can update a specific symbol or all symbols
    in the database.

    Examples:
        kavzitrader data historical update --symbol BTCUSDT --interval 1h
        kavzitrader data historical update --interval 1h
    """
    # Get configuration
    app_config: AppConfig = ctx.obj["app_config"]

    # Get API credentials from config
    api_key = app_config.api.binance.api_key
    api_secret = app_config.api.binance.api_secret

    # Initialize client
    client = BinanceHistoricalDataClient(
        api_key=api_key,
        api_secret=api_secret,
        max_workers=max_workers,
        batch_size=batch_size,
    )

    # Get database from context
    db: AsyncDatabase = ctx.obj["db"]

    async with db.session_scope() as db_session:
        service = HistoricalDownloadService(client, db_session)

        # Calculate start time based on days_back
        start_time = utc_now() - timedelta(days=days_back)
        end_time = utc_now()

        if symbol:
            # Update a specific symbol
            logger.info(
                "Updating %s %s data from %s to now",
                symbol,
                interval,
                start_time,
            )

            try:
                # Create download config
                config = SymbolicDownloadBatchConfigSchema(
                    symbol=symbol,
                    interval=interval,
                    start_time=start_time,
                    end_time=end_time,
                    batch_size=batch_size,
                    max_workers=max_workers,
                )

                # Download data
                data = await service.download_klines(config=config)

                # Report results
                click.echo(
                    f"Successfully updated {len(data)} records for {symbol} {interval}",
                )
                click.echo("Data saved to database")

            except Exception as e:
                logger.exception("Error updating historical data")
                raise click.ClickException(f"Failed to update data: {e!s}") from e
        else:
            # TODO: Implement updating all symbols in the database
            # This would require querying the database for existing symbols
            # and updating each one
            click.echo("Updating all symbols is not yet implemented")
            click.echo("Please specify a symbol using the --symbol option")
