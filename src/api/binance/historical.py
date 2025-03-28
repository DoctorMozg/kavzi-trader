"""
Binance Historical Data Client.

This module provides a specialized client for downloading large amounts of historical data
from Binance efficiently, with support for batching, parallelization, and rate limiting.
"""

from enum import Enum
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypeVar

import dateparser
import pandas as pd
from pydantic import BaseModel
from tqdm import tqdm

from src.api.binance.client import BinanceClient
from src.api.binance.constants import KLINE_INTERVALS
from src.api.common.exceptions import APIError, RateLimitError
from src.api.common.models import CandlestickSchema, TradeSchema

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class DataSaveFormat(str, Enum):
    """Data save format options."""

    CSV = "csv"
    PARQUET = "parquet"
    JSON = "json"


@dataclass
class DownloadBatchConfig:
    """Configuration for a download batch."""

    symbol: str
    interval: str
    start_time: datetime
    end_time: datetime
    batch_size: int = 1000
    max_workers: int = 4
    save_format: DataSaveFormat = DataSaveFormat.PARQUET
    output_dir: str = "./data"


class BinanceHistoricalDataClient:
    """
    Client for downloading large amounts of historical data from Binance efficiently.

    This client extends the standard BinanceClient with specialized methods for
    batch downloading and processing historical data with:
    - Parallel downloads using ThreadPoolExecutor
    - Smart batching to maximize throughput
    - Automatic rate limiting
    - Multiple output formats
    - Progress tracking
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        timeout: int = 60,
        max_workers: int = 4,
        batch_size: int = 1000,
        output_dir: str = "./data",
        save_format: DataSaveFormat = DataSaveFormat.PARQUET,
        proxies: dict[str, str] | None = None,
    ):
        """
        Initialize the Binance Historical Data Client.

        Args:
            api_key: Binance API key (optional)
            api_secret: Binance API secret (optional)
            testnet: Whether to use testnet
            timeout: Request timeout in seconds
            max_workers: Maximum number of concurrent download workers
            batch_size: Default size of each download batch
            output_dir: Default directory to save downloaded data
            save_format: Default format to save data (csv, parquet, json)
            proxies: Proxy configuration for requests
        """
        self.client = BinanceClient(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            timeout=timeout,
            proxies=proxies,
        )
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.output_dir = output_dir
        self.save_format = save_format

        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def date_to_milliseconds(date_str: str) -> int:
        """
        Convert a date string to milliseconds.

        Args:
            date_str: Date string in readable format, e.g., "1 Jan, 2020", "1 hour ago UTC"

        Returns:
            Milliseconds since epoch
        """
        # Parse the date with dateparser
        parsed_date = dateparser.parse(date_str)
        if not parsed_date:
            raise ValueError(f"Could not parse date string: {date_str}")

        # Return timestamp in milliseconds
        return int(parsed_date.timestamp() * 1000)

    @staticmethod
    def milliseconds_to_datetime(milliseconds: int) -> datetime:
        """
        Convert milliseconds to datetime.

        Args:
            milliseconds: Milliseconds since epoch

        Returns:
            Datetime object
        """
        return datetime.fromtimestamp(milliseconds / 1000)

    def _get_batch_intervals(
        self,
        start_time: datetime,
        end_time: datetime,
        interval: str,
        batch_size: int,
    ) -> list[dict[str, Any]]:
        """
        Split a time range into batches for efficient downloading.

        Args:
            start_time: Start time for the download
            end_time: End time for the download
            interval: Kline interval (e.g., "1m", "1h", "1d")
            batch_size: Maximum number of records per batch

        Returns:
            List of batch configurations with start_time and end_time
        """
        # Convert interval to milliseconds
        interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000

        # Calculate batch duration based on interval and batch size
        batch_duration_ms = interval_ms * batch_size

        # Convert datetime to milliseconds
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        # Create batch intervals
        batches = []
        batch_start = start_ms

        while batch_start < end_ms:
            batch_end = min(batch_start + batch_duration_ms, end_ms)
            batches.append(
                {
                    "start_time": batch_start,
                    "end_time": batch_end,
                },
            )
            batch_start = batch_end + 1  # Avoid overlap

        return batches

    def _save_data(
        self,
        data: list[T],
        symbol: str,
        data_type: str,
        interval: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        save_format: DataSaveFormat | None = None,
        output_dir: str | None = None,
    ) -> str:
        """
        Save data to a file.

        Args:
            data: Data to save
            symbol: Trading pair symbol
            data_type: Type of data (klines, trades, etc.)
            interval: Kline interval if applicable
            start_time: Start time for the data
            end_time: End time for the data
            save_format: Format to save data (defaults to self.save_format)
            output_dir: Directory to save data (defaults to self.output_dir)

        Returns:
            Path to the saved file
        """
        if not data:
            logger.warning(f"No data to save for {symbol} {data_type}")
            return ""

        # Use defaults if not specified
        format_to_use = save_format or self.save_format
        dir_to_use = output_dir or self.output_dir

        # Create directory if it doesn't exist
        Path(dir_to_use).mkdir(parents=True, exist_ok=True)

        # Create filename based on data type and time range
        time_suffix = ""
        if start_time and end_time:
            time_suffix = (
                f"{start_time.strftime('%Y%m%d')}_to_{end_time.strftime('%Y%m%d')}"
            )

        interval_part = f"_{interval}" if interval else ""
        filename_base = f"{symbol}_{data_type}{interval_part}_{time_suffix}"

        # Create pandas DataFrame from data
        df = pd.DataFrame([item.model_dump() for item in data])

        # Save according to specified format
        if format_to_use == DataSaveFormat.CSV:
            filepath = os.path.join(dir_to_use, f"{filename_base}.csv")
            df.to_csv(filepath, index=False)
        elif format_to_use == DataSaveFormat.PARQUET:
            filepath = os.path.join(dir_to_use, f"{filename_base}.parquet")
            df.to_parquet(filepath, index=False)
        elif format_to_use == DataSaveFormat.JSON:
            filepath = os.path.join(dir_to_use, f"{filename_base}.json")
            df.to_json(filepath, orient="records", date_format="iso")
        else:
            raise ValueError(f"Unsupported save format: {format_to_use}")

        logger.info(f"Saved {len(data)} records to {filepath}")
        return filepath

    async def download_klines(
        self,
        symbol: str,
        interval: str,
        start_time: str | datetime,
        end_time: str | datetime | None = None,
        batch_size: int | None = None,
        max_workers: int | None = None,
        save_format: DataSaveFormat | None = None,
        output_dir: str | None = None,
        save_progress: bool = True,
    ) -> list[CandlestickSchema]:
        """
        Download historical klines (candlestick) data.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            interval: Kline interval (e.g., "1m", "1h", "1d")
            start_time: Start time for the download (string or datetime)
            end_time: End time for the download (string or datetime, defaults to now)
            batch_size: Size of each download batch (defaults to self.batch_size)
            max_workers: Maximum number of concurrent workers (defaults to self.max_workers)
            save_format: Format to save data (defaults to self.save_format)
            output_dir: Directory to save data (defaults to self.output_dir)
            save_progress: Whether to save each batch as it completes

        Returns:
            List of candlestick data
        """
        # Process input parameters
        if isinstance(start_time, str):
            start_time_dt = dateparser.parse(start_time)
            if not start_time_dt:
                raise ValueError(f"Could not parse start_time: {start_time}")
        else:
            start_time_dt = start_time

        if end_time is None:
            end_time_dt = datetime.now()
        elif isinstance(end_time, str):
            end_time_dt = dateparser.parse(end_time)
            if not end_time_dt:
                raise ValueError(f"Could not parse end_time: {end_time}")
        else:
            end_time_dt = end_time

        batch_size_to_use = batch_size or self.batch_size
        max_workers_to_use = max_workers or self.max_workers

        # Get batch intervals
        batches = self._get_batch_intervals(
            start_time=start_time_dt,
            end_time=end_time_dt,
            interval=interval,
            batch_size=batch_size_to_use,
        )

        # Prepare for downloads
        all_data: list[CandlestickSchema] = []

        # Set up ThreadPoolExecutor for parallel downloads
        with ThreadPoolExecutor(max_workers=max_workers_to_use) as executor:
            futures = []

            # Create download tasks for each batch
            for batch in batches:
                batch_start = self.milliseconds_to_datetime(batch["start_time"])
                batch_end = self.milliseconds_to_datetime(batch["end_time"])

                # Submit download task
                future = executor.submit(
                    self._download_klines_batch,
                    symbol=symbol,
                    interval=interval,
                    start_time=batch_start,
                    end_time=batch_end,
                )
                futures.append((future, batch_start, batch_end))

            # Process results with progress bar
            with tqdm(
                total=len(futures),
                desc=f"Downloading {symbol} {interval} klines",
            ) as pbar:
                for future, batch_start, batch_end in futures:
                    try:
                        batch_data = future.result()
                        if batch_data:
                            all_data.extend(batch_data)

                            # Save batch data if requested
                            if save_progress:
                                self._save_data(
                                    data=batch_data,
                                    symbol=symbol,
                                    data_type="klines",
                                    interval=interval,
                                    start_time=batch_start,
                                    end_time=batch_end,
                                    save_format=save_format,
                                    output_dir=output_dir,
                                )

                        pbar.update(1)
                    except Exception as e:
                        logger.error(
                            f"Error downloading batch {batch_start} to {batch_end}: {e}",
                        )
                        pbar.update(1)

        # Save all data if requested and not already saved by batch
        if all_data and not save_progress:
            self._save_data(
                data=all_data,
                symbol=symbol,
                data_type="klines",
                interval=interval,
                start_time=start_time_dt,
                end_time=end_time_dt,
                save_format=save_format,
                output_dir=output_dir,
            )

        return all_data

    def _download_klines_batch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CandlestickSchema]:
        """
        Download a batch of klines.

        Args:
            symbol: Trading pair symbol
            interval: Kline interval
            start_time: Start time for the batch
            end_time: End time for the batch

        Returns:
            List of candlestick data
        """
        max_retries = 3
        retry_delay = 2  # seconds

        for retry in range(max_retries):
            try:
                # Get klines using the standard client
                klines = self.client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time=start_time,
                    end_time=end_time,
                    limit=1000,  # Maximum allowed by Binance
                )
                return klines

            except RateLimitError as e:
                # Handle rate limiting with exponential backoff
                wait_time = retry_delay * (2**retry)
                logger.warning(f"Rate limit hit, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)

            except APIError as e:
                logger.error(f"API error downloading klines: {e}")
                # Only retry certain errors
                if "timeout" in str(e).lower() or "5xx" in str(e):
                    time.sleep(retry_delay)
                else:
                    raise

        # If we get here, all retries failed
        logger.error(f"Failed to download klines after {max_retries} retries")
        return []

    async def download_trades(
        self,
        symbol: str,
        start_time: str | datetime,
        end_time: str | datetime | None = None,
        batch_size: int | None = None,
        max_workers: int | None = None,
        save_format: DataSaveFormat | None = None,
        output_dir: str | None = None,
        save_progress: bool = True,
    ) -> list[TradeSchema]:
        """
        Download historical trades data.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            start_time: Start time for the download (string or datetime)
            end_time: End time for the download (string or datetime, defaults to now)
            batch_size: Size of each download batch (defaults to self.batch_size)
            max_workers: Maximum number of concurrent workers (defaults to self.max_workers)
            save_format: Format to save data (defaults to self.save_format)
            output_dir: Directory to save data (defaults to self.output_dir)
            save_progress: Whether to save each batch as it completes

        Returns:
            List of trade data
        """
        # Process input parameters
        if isinstance(start_time, str):
            start_time_dt = dateparser.parse(start_time)
            if not start_time_dt:
                raise ValueError(f"Could not parse start_time: {start_time}")
        else:
            start_time_dt = start_time

        if end_time is None:
            end_time_dt = datetime.now()
        elif isinstance(end_time, str):
            end_time_dt = dateparser.parse(end_time)
            if not end_time_dt:
                raise ValueError(f"Could not parse end_time: {end_time}")
        else:
            end_time_dt = end_time

        # Trades require a different batching strategy - we'll use time windows
        # Split the time range into days, which is a reasonable batch size for trades
        current_start = start_time_dt
        batches = []

        while current_start < end_time_dt:
            current_end = min(current_start + timedelta(days=1), end_time_dt)
            batches.append(
                {
                    "start_time": current_start,
                    "end_time": current_end,
                },
            )
            current_start = current_end

        # Prepare for downloads
        all_data: list[TradeSchema] = []
        max_workers_to_use = max_workers or self.max_workers

        # Set up ThreadPoolExecutor for parallel downloads
        with ThreadPoolExecutor(max_workers=max_workers_to_use) as executor:
            futures = []

            # Create download tasks for each batch
            for batch in batches:
                # Submit download task
                future = executor.submit(
                    self._download_trades_batch,
                    symbol=symbol,
                    start_time=batch["start_time"],
                    end_time=batch["end_time"],
                )
                futures.append((future, batch["start_time"], batch["end_time"]))

            # Process results with progress bar
            with tqdm(total=len(futures), desc=f"Downloading {symbol} trades") as pbar:
                for future, batch_start, batch_end in futures:
                    try:
                        batch_data = future.result()
                        if batch_data:
                            all_data.extend(batch_data)

                            # Save batch data if requested
                            if save_progress:
                                self._save_data(
                                    data=batch_data,
                                    symbol=symbol,
                                    data_type="trades",
                                    start_time=batch_start,
                                    end_time=batch_end,
                                    save_format=save_format,
                                    output_dir=output_dir,
                                )

                        pbar.update(1)
                    except Exception as e:
                        logger.error(
                            f"Error downloading trades batch {batch_start} to {batch_end}: {e}",
                        )
                        pbar.update(1)

        # Save all data if requested and not already saved by batch
        if all_data and not save_progress:
            self._save_data(
                data=all_data,
                symbol=symbol,
                data_type="trades",
                start_time=start_time_dt,
                end_time=end_time_dt,
                save_format=save_format,
                output_dir=output_dir,
            )

        return all_data

    def _download_trades_batch(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[TradeSchema]:
        """
        Download a batch of trades.

        Args:
            symbol: Trading pair symbol
            start_time: Start time for the batch
            end_time: End time for the batch

        Returns:
            List of trade data
        """
        max_retries = 3
        retry_delay = 2  # seconds

        # For trades, we need to use historical_trades with fromId
        # First, get the trade ID close to our start time
        for retry in range(max_retries):
            try:
                # Convert times to milliseconds
                start_ms = int(start_time.timestamp() * 1000)
                end_ms = int(end_time.timestamp() * 1000)

                # First, get trades around our start time
                first_trades = self.client.get_historical_trades(
                    symbol=symbol,
                    limit=1,
                    start_time=start_ms,
                )

                if not first_trades:
                    return []

                from_id = first_trades[0].id
                all_trades = []

                # Keep fetching trades until we reach the end time
                while True:
                    batch = self.client.get_historical_trades(
                        symbol=symbol,
                        limit=1000,
                        from_id=from_id,
                    )

                    if not batch:
                        break

                    # Filter trades by time
                    valid_trades = [
                        t
                        for t in batch
                        if start_ms <= int(t.time.timestamp() * 1000) <= end_ms
                    ]

                    all_trades.extend(valid_trades)

                    # Check if we've reached the end time
                    last_trade_time = int(batch[-1].time.timestamp() * 1000)
                    if last_trade_time > end_ms:
                        break

                    # Update from_id for next iteration
                    from_id = batch[-1].id + 1

                    # Avoid rate limiting
                    time.sleep(0.1)

                return all_trades

            except RateLimitError as e:
                # Handle rate limiting with exponential backoff
                wait_time = retry_delay * (2**retry)
                logger.warning(f"Rate limit hit, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)

            except APIError as e:
                logger.error(f"API error downloading trades: {e}")
                # Only retry certain errors
                if "timeout" in str(e).lower() or "5xx" in str(e):
                    time.sleep(retry_delay)
                else:
                    raise

        # If we get here, all retries failed
        logger.error(f"Failed to download trades after {max_retries} retries")
        return []

    async def download_multiple_symbols(
        self,
        config: DownloadBatchConfig,
        symbols: list[str],
    ) -> dict[str, str]:
        """
        Download data for multiple symbols with the same configuration.

        Args:
            config: Download configuration
            symbols: List of symbols to download

        Returns:
            Dictionary of symbol to file path
        """
        results = {}

        for symbol in symbols:
            try:
                if config.interval:  # Klines
                    data = await self.download_klines(
                        symbol=symbol,
                        interval=config.interval,
                        start_time=config.start_time,
                        end_time=config.end_time,
                        batch_size=config.batch_size,
                        max_workers=config.max_workers,
                        save_format=config.save_format,
                        output_dir=config.output_dir,
                    )

                    # Record the result
                    if data:
                        filepath = self._save_data(
                            data=data,
                            symbol=symbol,
                            data_type="klines",
                            interval=config.interval,
                            start_time=config.start_time,
                            end_time=config.end_time,
                            save_format=config.save_format,
                            output_dir=config.output_dir,
                        )
                        results[symbol] = filepath

            except Exception as e:
                logger.error(f"Error downloading data for {symbol}: {e}")

        return results

    async def download_all_symbols(
        self,
        interval: str,
        start_time: str | datetime,
        end_time: str | datetime | None = None,
        quote_asset: str | None = None,
        min_volume: float | None = None,
        batch_size: int | None = None,
        max_workers: int | None = None,
        save_format: DataSaveFormat | None = None,
        output_dir: str | None = None,
    ) -> dict[str, str]:
        """
        Download data for all available symbols matching criteria.

        Args:
            interval: Kline interval (e.g., "1m", "1h", "1d")
            start_time: Start time for the download
            end_time: End time for the download (defaults to now)
            quote_asset: Filter symbols by quote asset (e.g., "USDT")
            min_volume: Minimum 24h volume in USD
            batch_size: Size of each download batch
            max_workers: Maximum number of concurrent workers
            save_format: Format to save data
            output_dir: Directory to save data

        Returns:
            Dictionary of symbol to file path
        """
        # Get exchange information to find available symbols
        exchange_info = self.client.get_exchange_info()
        all_symbols = exchange_info.get("symbols", [])

        # Filter symbols
        filtered_symbols = []

        # Get 24h ticker data for volume filtering if needed
        tickers = None
        if min_volume:
            tickers = self.client.get_all_tickers()
            # Create a lookup dictionary
            ticker_map = {t.symbol: t for t in tickers}

        for symbol_info in all_symbols:
            symbol = symbol_info.get("symbol")
            status = symbol_info.get("status")

            # Skip inactive symbols
            if status != "TRADING":
                continue

            # Filter by quote asset if specified
            if quote_asset and symbol_info.get("quoteAsset") != quote_asset:
                continue

            # Filter by volume if specified and tickers are available
            if min_volume and tickers:
                ticker = ticker_map.get(symbol)
                if not ticker or (ticker.volume and float(ticker.volume) < min_volume):
                    continue

            filtered_symbols.append(symbol)

        # Create download config
        config = DownloadBatchConfig(
            symbol="",  # Will be set per download
            interval=interval,
            start_time=start_time
            if isinstance(start_time, datetime)
            else dateparser.parse(start_time),
            end_time=end_time
            if isinstance(end_time, datetime) or end_time is None
            else dateparser.parse(end_time) or datetime.now(),
            batch_size=batch_size or self.batch_size,
            max_workers=max_workers or self.max_workers,
            save_format=save_format or self.save_format,
            output_dir=output_dir or self.output_dir,
        )

        # Download data for filtered symbols
        return await self.download_multiple_symbols(config, filtered_symbols)
