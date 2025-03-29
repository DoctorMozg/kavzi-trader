#!/usr/bin/env python3
"""
Binance Historical Data Download Example

This script demonstrates how to use the BinanceHistoricalDataClient to download
large amounts of historical data from Binance efficiently.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from src.api.binance.historical import (
    BinanceHistoricalDataClient,
    DownloadBatchConfigSchema,
)
from src.commons.time_utility import utc_now

# Add src to path to allow imports from src package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set up logging
from src.commons.logging import setup_logging

# Initialize logger
logger = setup_logging(name="historical_data_example")


def print_section(title: str) -> None:
    """Print a section title with formatting."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")


def download_single_symbol_example() -> None:
    """Download historical data for a single symbol."""
    print_section("Downloading Historical Data for a Single Symbol")

    # Create the historical data client
    client = BinanceHistoricalDataClient(testnet=False)  # Use real Binance API

    # Define the time range (last 30 days)
    end_time = datetime.now(tz=ZoneInfo("UTC"))
    start_time = end_time - timedelta(days=30)

    # Create output directory if it doesn't exist
    output_dir = Path("./data/single_symbol_example")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download 1-hour kline data for Bitcoin
    print("Downloading 1-hour kline data for BTCUSDT (last 30 days)...")
    klines = client.download_klines(
        symbol="BTCUSDT",
        interval="1h",
        start_time=start_time,
        end_time=end_time,
        output_dir=output_dir,
    )

    print(f"Downloaded {len(klines)} candlesticks for BTCUSDT")

    # Print the first 3 candlesticks
    for i, candle in enumerate(klines[:3], 1):
        print(
            f"Candle {i}: "
            f"Open time={candle.open_time}, "
            f"Close price={candle.close_price}, "
            f"Volume={candle.volume}",
        )


def download_multiple_timeframes_example() -> None:
    """Download data for different timeframes."""
    print_section("Downloading Multiple Timeframes")

    # Create the historical data client
    client = BinanceHistoricalDataClient(testnet=False)

    # Define the time range with timezone
    now = utc_now()

    # Create output directory if it doesn't exist
    output_dir = Path("./data/multiple_timeframes")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define different timeframes and their corresponding time ranges
    timeframes: list[dict[str, str | int]] = [
        {"interval": "15m", "days": 7},
        {"interval": "1h", "days": 30},
        {"interval": "4h", "days": 60},
        {"interval": "1d", "days": 365},
    ]

    # Download data for each timeframe
    for tf in timeframes:
        interval = cast(str, tf["interval"])
        days = cast(int, tf["days"])
        start_time = now - timedelta(days=days)

        print(f"Downloading {interval} kline data for ETHUSDT (last {days} days)...")
        klines = client.download_klines(
            symbol="ETHUSDT",
            interval=interval,
            start_time=start_time,
            end_time=now,
            output_dir=output_dir / f"ETHUSDT_{interval}",
        )

        print(f"Downloaded {len(klines)} {interval} candlesticks for ETHUSDT")


def download_trades_example() -> None:
    """Download historical trades data."""
    print_section("Downloading Historical Trades")

    # Create the historical data client
    client = BinanceHistoricalDataClient(testnet=False)

    # Define a shorter time range for trades (last 1 day)
    end_time = datetime.now(tz=ZoneInfo("UTC"))
    start_time = end_time - timedelta(days=1)

    # Create output directory if it doesn't exist
    output_dir = Path("./data/trades")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download trades for Bitcoin
    print("Downloading trades for BTCUSDT (last 24 hours)...")
    trades = client.download_trades(
        symbol="BTCUSDT",
        start_time=start_time,
        end_time=end_time,
        output_dir=output_dir,
    )

    print(f"Downloaded {len(trades)} trades for BTCUSDT")

    # Print the first 3 trades
    for i, trade in enumerate(trades[:3], 1):
        print(
            f"Trade {i}: "
            f"Time={trade.time}, "
            f"Price={trade.price}, "
            f"Quantity={trade.qty}",
        )


def download_multiple_symbols_example() -> None:
    """Download data for multiple symbols simultaneously."""
    print_section("Downloading Data for Multiple Symbols")

    # Create the historical data client with more workers for parallel downloads
    client = BinanceHistoricalDataClient(testnet=False, max_workers=8)

    # Define the time range (last 7 days)
    end_time = datetime.now(tz=ZoneInfo("UTC"))
    start_time = end_time - timedelta(days=7)

    # Create output directory if it doesn't exist
    output_dir = Path("./data/multiple_symbols")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define a list of symbols
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"]

    # Create a download configuration
    config = DownloadBatchConfigSchema(
        symbol="",  # Will be set per download in the method
        interval="4h",
        start_time=start_time,
        end_time=end_time,
        batch_size=500,
        max_workers=4,
        output_dir=output_dir,
    )

    # Download data for all symbols
    print(f"Downloading 4h kline data for {len(symbols)} symbols (last 7 days)...")
    results = client.download_multiple_symbols(config, symbols)

    # Print results
    for symbol, filepath in results.items():
        filename = filepath.name if filepath else "Failed"
        print(f"{symbol}: {filename}")


def download_usdt_pairs_example() -> None:
    """Download data for all USDT trading pairs with filtering."""
    print_section("Downloading Data for USDT Trading Pairs")

    # Create the historical data client with more workers
    client = BinanceHistoricalDataClient(testnet=False, max_workers=8)

    # Define a shorter time range (last 2 days)
    end_time = datetime.now(tz=ZoneInfo("UTC"))
    start_time = end_time - timedelta(days=2)

    # Create output directory if it doesn't exist
    output_dir = Path("./data/usdt_pairs")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download data for all USDT pairs with minimum volume
    print("Downloading 1h kline data for all USDT pairs with min 24h volume...")
    print("Minimum volume: 5,000,000 USDT")
    results = client.download_all_symbols(
        interval="1h",
        start_time=start_time,
        end_time=end_time,
        quote_asset="USDT",
        min_volume=5_000_000,  # Minimum 24h volume in USDT
        output_dir=output_dir,
    )

    # Print summary
    print(f"Successfully downloaded data for {len(results)} symbols")

    # Print first 5 results
    for i, (symbol, filepath) in enumerate(list(results.items())[:5], 1):
        filename = filepath.name if filepath else "Failed"
        print(f"{i}. {symbol}: {filename}")


def main() -> None:
    """Run the examples."""
    try:
        # Example 1: Download data for a single symbol
        download_single_symbol_example()

        # Example 2: Download data for multiple timeframes
        download_multiple_timeframes_example()

        # Example 3: Download trades data
        download_trades_example()

        # Example 4: Download data for multiple symbols
        download_multiple_symbols_example()

        # Example 5: Download data for all USDT pairs with filtering
        download_usdt_pairs_example()

    except Exception:
        logger.exception("Error in examples")


if __name__ == "__main__":
    # Run the examples
    main()
