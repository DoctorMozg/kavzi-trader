"""
CLI commands for historical data collection.

This module provides command-line interface commands for fetching,
updating, validating, and managing historical market data.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import click
import dateparser
from tabulate import tabulate

from src.cli.decorators import database_connection_required
from src.commons.time_utility import utc_now
from src.data.collection.historical.fetcher import HistoricalDataFetcher
from src.data.storage.database import Database

logger = logging.getLogger(__name__)


@click.group(name="historical")
def historical_command():
    """Commands for managing historical market data."""
    pass


@historical_command.command(name="fetch")
@click.option(
    "--symbol",
    required=True,
    help="Trading pair symbol (e.g., BTCUSDT)"
)
@click.option(
    "--interval",
    required=True,
    help="Timeframe interval (e.g., 1m, 1h, 1d)"
)
@click.option(
    "--start-date",
    help="Start date for historical data (YYYY-MM-DD or relative like '1 year ago')"
)
@click.option(
    "--end-date",
    help="End date for historical data (YYYY-MM-DD or relative like 'yesterday')"
)
@click.option(
    "--days",
    type=int,
    help="Number of days to fetch (alternative to start-date)"
)
@click.option(
    "--force-full",
    is_flag=True,
    help="Force full download instead of incremental"
)
@click.option(
    "--batch-size",
    type=int,
    default=1000,
    help="Number of candles per batch"
)
@click.option(
    "--workers",
    type=int,
    default=4,
    help="Number of parallel workers"
)
@click.option(
    "--no-validate",
    is_flag=True,
    help="Skip data validation"
)
@click.option(
    "--store-csv",
    is_flag=True,
    help="Also store data as CSV files"
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Output directory for CSV files"
)
@database_connection_required
def fetch_historical(
    database: Database,
    symbol: str,
    interval: str,
    start_date: Optional[str],
    end_date: Optional[str],
    days: Optional[int],
    force_full: bool,
    batch_size: int,
    workers: int,
    no_validate: bool,
    store_csv: bool,
    output_dir: Optional[Path]
):
    """
    Fetch historical market data for a symbol and interval.
    
    Examples:
        kavzitrader data historical fetch --symbol BTCUSDT --interval 1h --days 30
        kavzitrader data historical fetch --symbol ETHUSDT --interval 1d --start-date "2023-01-01"
    """
    # Parse dates
    end_time = dateparser.parse(end_date) if end_date else utc_now()
    
    if start_date:
        start_time = dateparser.parse(start_date)
    elif days:
        start_time = end_time - timedelta(days=days)
    else:
        # Default to 30 days if nothing specified
        start_time = end_time - timedelta(days=30)
        click.echo(f"No start date specified, defaulting to {start_time.date()}")
    
    click.echo(f"Fetching historical data for {symbol} {interval}")
    click.echo(f"Time range: {start_time} to {end_time}")
    
    # Create fetcher and run
    fetcher = HistoricalDataFetcher(
        database=database,
        batch_size=batch_size,
        max_workers=workers,
        output_dir=output_dir
    )
    
    result = fetcher.fetch_historical_data(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        force_full=force_full,
        validate=not no_validate,
        store_csv=store_csv,
        output_dir=output_dir
    )
    
    # Display results
    if "error" in result:
        click.echo(f"Error: {result['error']}")
        return
    
    click.echo("\nCollection completed successfully!")
    click.echo(f"Records processed: {result['records_processed']}")
    click.echo(f"Records inserted: {result['records_inserted']}")
    click.echo(f"Records updated: {result['records_updated']}")
    
    if not no_validate:
        click.echo("\nValidation results:")
        if result['validation']['valid']:
            click.echo("  ✅ All data is valid")
        else:
            click.echo("  ⚠️ Validation issues found:")
            for issue in result['validation']['issues']:
                click.echo(f"  - {issue}")
        
        if result['validation']['warnings']:
            click.echo("\nValidation warnings:")
            for warning in result['validation']['warnings'][:5]:
                click.echo(f"  - {warning}")
            
            if len(result['validation']['warnings']) > 5:
                click.echo(f"  ... and {len(result['validation']['warnings']) - 5} more warnings")
    
    metrics = result['metrics']
    click.echo("\nPerformance metrics:")
    click.echo(f"  Time taken: {metrics['elapsed_formatted']}")
    click.echo(f"  Throughput: {metrics['performance']['throughput_formatted']}")
    click.echo(f"  API calls: {metrics['api']['calls']} (errors: {metrics['api']['errors']})")
    click.echo(f"  Batches completed: {metrics['batches']['completed']}")


@historical_command.command(name="update")
@click.option(
    "--symbol",
    required=True,
    help="Trading pair symbol or 'all' for all available"
)
@click.option(
    "--interval",
    required=True,
    help="Timeframe interval or 'all' for all available"
)
@click.option(
    "--days",
    type=int,
    default=7,
    help="Number of days to look back for updates"
)
@click.option(
    "--workers",
    type=int,
    default=4,
    help="Number of parallel workers"
)
@database_connection_required
def update_historical(
    database: Database,
    symbol: str,
    interval: str,
    days: int,
    workers: int
):
    """
    Update historical market data to the latest available.
    
    Examples:
        kavzitrader data historical update --symbol BTCUSDT --interval 1h
        kavzitrader data historical update --symbol all --interval all --days 3
    """
    end_time = utc_now()
    start_time = end_time - timedelta(days=days)
    
    fetcher = HistoricalDataFetcher(
        database=database,
        max_workers=workers
    )
    
    # TODO: Implement 'all' handling for multiple symbols/intervals
    if symbol.lower() == 'all' or interval.lower() == 'all':
        click.echo("Update for all symbols/intervals not yet implemented")
        return
    
    click.echo(f"Updating historical data for {symbol} {interval}")
    click.echo(f"Looking back {days} days from {end_time}")
    
    # Run the fetch with incremental update
    result = fetcher.fetch_historical_data(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        force_full=False  # Use incremental update
    )
    
    # Display results
    if "error" in result:
        click.echo(f"Error: {result['error']}")
        return
    
    if result['records_processed'] == 0:
        click.echo("No new data to update - already up to date!")
    else:
        click.echo(f"Updated {result['records_processed']} records")
        click.echo(f"Inserted: {result['records_inserted']}, Updated: {result['records_updated']}")


@historical_command.command(name="validate")
@click.option(
    "--symbol",
    required=True,
    help="Trading pair symbol"
)
@click.option(
    "--interval",
    required=True,
    help="Timeframe interval"
)
@click.option(
    "--start-date",
    help="Start date for validation (YYYY-MM-DD)"
)
@click.option(
    "--end-date",
    help="End date for validation (YYYY-MM-DD)"
)
@click.option(
    "--days",
    type=int,
    help="Number of days to validate (alternative to date range)"
)
@click.option(
    "--fix-gaps",
    is_flag=True,
    help="Automatically fix any gaps found"
)
@database_connection_required
def validate_historical(
    database: Database,
    symbol: str,
    interval: str,
    start_date: Optional[str],
    end_date: Optional[str],
    days: Optional[int],
    fix_gaps: bool
):
    """
    Validate historical market data for a symbol and interval.
    
    Examples:
        kavzitrader data historical validate --symbol BTCUSDT --interval 1h
        kavzitrader data historical validate --symbol ETHUSDT --interval 1d --fix-gaps
    """
    # Parse dates
    end_time = dateparser.parse(end_date) if end_date else utc_now()
    
    if start_date:
        start_time = dateparser.parse(start_date)
    elif days:
        start_time = end_time - timedelta(days=days)
    else:
        # Default to all data
        start_time = None
    
    fetcher = HistoricalDataFetcher(database=database)
    
    click.echo(f"Validating historical data for {symbol} {interval}")
    if start_time and end_time:
        click.echo(f"Time range: {start_time} to {end_time}")
    else:
        click.echo("Validating all available data")
    
    # Run validation
    result = fetcher.validate_data_integrity(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time
    )
    
    # Display results
    if result['count'] == 0:
        click.echo("No data found for the specified range")
        return
    
    click.echo(f"\nFound {result['count']} records")
    
    if result['valid']:
        click.echo("✅ Data integrity check passed - no issues found")
    else:
        click.echo("⚠️ Data integrity issues found:")
        for issue in result['issues']:
            click.echo(f"  - {issue}")
    
    if result['gaps']:
        click.echo(f"\nFound {len(result['gaps'])} gaps in the data:")
        for i, gap in enumerate(result['gaps'][:5]):
            click.echo(f"  {i+1}. {gap['start']} to {gap['end']} ({gap['duration_hours']:.1f} hours)")
        
        if len(result['gaps']) > 5:
            click.echo(f"  ... and {len(result['gaps']) - 5} more gaps")
        
        if fix_gaps:
            click.echo("\nFixing gaps...")
            # TODO: Implement gap fixing with incremental fetching
            click.echo("Gap fixing not yet implemented")
    
    # Data summary
    summary = fetcher.get_data_summary(symbol, interval)
    click.echo("\nData summary:")
    click.echo(f"  First record: {summary.get('first_timestamp')}")
    click.echo(f"  Last record: {summary.get('last_timestamp')}")
    click.echo(f"  Duration: {summary.get('duration_days', 0):.1f} days")


@historical_command.command(name="list")
@click.option(
    "--format",
    type=click.Choice(['table', 'csv']),
    default='table',
    help="Output format"
)
@database_connection_required
def list_historical(database: Database, format: str):
    """
    List available historical data in the database.
    
    Examples:
        kavzitrader data historical list
        kavzitrader data historical list --format csv
    """
    # This is a placeholder implementation
    # In a real implementation, this would query the database for unique symbol/interval pairs
    # and their corresponding data ranges
    
    click.echo("Listing available historical data:")
    click.echo("(This is a placeholder - not actually querying the database)")
    
    # Example data
    data = [
        ["BTCUSDT", "1m", "2023-01-01", "2023-07-31", 212344, "212.3"],
        ["BTCUSDT", "1h", "2022-01-01", "2023-07-31", 13450, "547.9"],
        ["ETHUSDT", "1h", "2022-06-01", "2023-07-31", 10156, "413.8"],
        ["BNBUSDT", "1d", "2021-01-01", "2023-07-31", 942, "942.0"],
    ]
    
    headers = ["Symbol", "Interval", "First Date", "Last Date", "Records", "Duration (days)"]
    
    if format == 'table':
        click.echo(tabulate(data, headers=headers, tablefmt="grid"))
    else:  # csv
        click.echo(",".join(headers))
        for row in data:
            click.echo(",".join(str(cell) for cell in row))


@historical_command.command(name="export")
@click.option(
    "--symbol",
    required=True,
    help="Trading pair symbol"
)
@click.option(
    "--interval",
    required=True,
    help="Timeframe interval"
)
@click.option(
    "--start-date",
    help="Start date for export (YYYY-MM-DD)"
)
@click.option(
    "--end-date",
    help="End date for export (YYYY-MM-DD)"
)
@click.option(
    "--days",
    type=int,
    help="Number of days to export (alternative to date range)"
)
@click.option(
    "--format",
    type=click.Choice(['csv', 'json', 'parquet']),
    default='csv',
    help="Export format"
)
@click.option(
    "--output",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    help="Output file path"
)
@database_connection_required
def export_historical(
    database: Database,
    symbol: str,
    interval: str,
    start_date: Optional[str],
    end_date: Optional[str],
    days: Optional[int],
    format: str,
    output: Optional[Path]
):
    """
    Export historical market data to a file.
    
    Examples:
        kavzitrader data historical export --symbol BTCUSDT --interval 1h --days 30 --format csv
        kavzitrader data historical export --symbol ETHUSDT --interval 1d --output eth_daily.csv
    """
    # Parse dates
    end_time = dateparser.parse(end_date) if end_date else utc_now()
    
    if start_date:
        start_time = dateparser.parse(start_date)
    elif days:
        start_time = end_time - timedelta(days=days)
    else:
        # Default to 30 days
        start_time = end_time - timedelta(days=30)
    
    # Generate default output filename if not provided
    if not output:
        output = Path(f"{symbol}_{interval}_{start_time.date()}_to_{end_time.date()}.{format}")
    
    click.echo(f"Exporting {symbol} {interval} data from {start_time} to {end_time}")
    click.echo(f"Output file: {output}")
    
    # TODO: Implement actual export functionality
    click.echo("Export functionality not yet implemented")
    click.echo("This would query the database and save data in the specified format") 