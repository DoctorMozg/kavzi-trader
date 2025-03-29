"""
Binance Historical Data Client.

This module provides a specialized client for downloading large amounts
of historical data
from Binance efficiently, with support for batching, parallelization, and
rate limiting.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

import dateparser
import pandas as pd
from pydantic import BaseModel, Field

from src.api.binance.client import BinanceClient
from src.api.binance.constants import KLINE_INTERVALS
from src.api.common.exceptions import APIError, RateLimitError
from src.api.common.models import CandlestickSchema, TradeSchema
from src.commons.time_utility import (
    MILLISECONDS_IN_SECOND,
    milliseconds_to_datetime,
    utc_now,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class DownloadBatchConfigSchema(BaseModel):
    """Configuration for a download batch."""

    symbol: str
    interval: str
    start_time: datetime
    end_time: datetime
    batch_size: int = Field(default=1000, gt=0)
    max_workers: int = Field(default=4, gt=0)
    output_dir: Path = Field(default=Path("./data"))


class BinanceHistoricalDataClient:
    """
    Client for downloading large amounts of historical data from Binance efficiently.

    This client extends the standard BinanceClient with specialized methods for
    batch downloading and processing historical data with:
    - Parallel downloads using ThreadPoolExecutor
    - Smart batching to maximize throughput
    - Automatic rate limiting
    - CSV output format
    - Progress tracking
    """

    def __init__(
        self,
        api_key: None | str = None,
        api_secret: None | str = None,
        testnet: bool = False,
        timeout: int = 60,
        max_workers: int = 4,
        batch_size: int = 1000,
        output_dir: Path = Path("./data"),
        proxies: None | dict[str, str] = None,
    ) -> None:
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

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)

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
        interval: None | str = None,
        start_time: None | datetime = None,
        end_time: None | datetime = None,
        output_dir: None | Path = None,
    ) -> Path:
        """
        Save data to a CSV file.

        Args:
            data: Data to save
            symbol: Trading pair symbol
            data_type: Type of data (klines, trades, etc.)
            interval: Kline interval if applicable
            start_time: Start time for the data
            end_time: End time for the data
            output_dir: Directory to save data (defaults to self.output_dir)

        Returns:
            Path to the saved file
        """
        if not data:
            logger.warning("No data to save for %s %s", symbol, data_type)
            return Path()  # Return empty Path to match return type

        # Use defaults if not specified
        dir_to_use = output_dir or self.output_dir

        # Create directory if it doesn't exist
        dir_to_use.mkdir(parents=True, exist_ok=True)

        # Create filename based on data type and time range
        time_suffix = ""
        if start_time and end_time:
            time_suffix = (
                f"{start_time.strftime('%Y%m%d')}_to_{end_time.strftime('%Y%m%d')}"
            )

        interval_part = f"_{interval}" if interval else ""
        filename_base = f"{symbol}_{data_type}{interval_part}_{time_suffix}"

        # Create pandas DataFrame from data
        data_df = pd.DataFrame([item.model_dump() for item in data])

        # Save to CSV
        filepath = dir_to_use / f"{filename_base}.csv"
        data_df.to_csv(filepath, index=False)

        logger.info("Saved %d records to %s", len(data), filepath)
        return filepath

    def download_klines(  # noqa: C901, PLR0912
        self,
        symbol: str,
        interval: str,
        start_time: str | datetime,
        end_time: None | str | datetime = None,
        batch_size: None | int = None,
        max_workers: None | int = None,
        output_dir: None | Path = None,
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
            max_workers: Maximum number of concurrent workers
            (defaults to self.max_workers)
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
            end_time_dt = utc_now()
        elif isinstance(end_time, str):
            end_time_dt = dateparser.parse(end_time)  # type: ignore
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

        logger.info(
            "Starting download of %s %s klines from %s to %s (%d batches)",
            symbol,
            interval,
            start_time_dt,
            end_time_dt,
            len(batches),
        )

        # Set up ThreadPoolExecutor for parallel downloads
        with ThreadPoolExecutor(max_workers=max_workers_to_use) as executor:
            futures = []

            # Create download tasks for each batch
            for batch in batches:
                batch_start = milliseconds_to_datetime(batch["start_time"])
                batch_end = milliseconds_to_datetime(batch["end_time"])

                # Submit download task
                future = executor.submit(
                    self._download_klines_batch,
                    symbol=symbol,
                    interval=interval,
                    start_time=batch_start,
                    end_time=batch_end,
                )
                futures.append((future, batch_start, batch_end))

            # Process results
            completed = 0
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
                                output_dir=output_dir,
                            )

                    completed += 1
                    logger.info(
                        "Completed batch %d/%d for %s %s klines (%.1f%%)",
                        completed,
                        len(futures),
                        symbol,
                        interval,
                        (completed / len(futures)) * 100,
                    )
                except Exception:
                    logger.exception(
                        "Error downloading batch %s to %s",
                        batch_start,
                        batch_end,
                    )
                    completed += 1

        logger.info(
            "Completed download of %s %s klines: %d records retrieved",
            symbol,
            interval,
            len(all_data),
        )

        # Save all data if requested and not already saved by batch
        if all_data and not save_progress:
            self._save_data(
                data=all_data,
                symbol=symbol,
                data_type="klines",
                interval=interval,
                start_time=start_time_dt,
                end_time=end_time_dt,
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
        try:
            # Get klines using the standard client
            klines = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                limit=1000,  # Maximum allowed by Binance
            )
        except RateLimitError as e:
            raise APIError("Rate limit hit") from e
        except APIError:
            logger.exception("API error downloading klines")
            raise
        else:
            return klines

    def download_trades(  # noqa: C901, PLR0912
        self,
        symbol: str,
        start_time: str | datetime,
        end_time: None | str | datetime = None,
        max_workers: None | int = None,
        output_dir: None | Path = None,
        save_progress: bool = True,
    ) -> list[TradeSchema]:
        """
        Download historical trades data.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            start_time: Start time for the download (string or datetime)
            end_time: End time for the download (string or datetime, defaults to now)
            batch_size: Size of each download batch (not used for trades)
            max_workers: Maximum number of concurrent workers
            (defaults to self.max_workers)
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
            end_time_dt = utc_now()
        elif isinstance(end_time, str):
            end_time_dt = dateparser.parse(end_time)  # type: ignore
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

        logger.info(
            "Starting download of %s trades from %s to %s (%d batches)",
            symbol,
            start_time_dt,
            end_time_dt,
            len(batches),
        )

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

            # Process results
            completed = 0
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
                                output_dir=output_dir,
                            )

                    completed += 1
                    logger.info(
                        "Completed batch %d/%d for %s trades (%.1f%%)",
                        completed,
                        len(futures),
                        symbol,
                        (completed / len(futures)) * 100,
                    )
                except Exception:
                    logger.exception(
                        "Error downloading trades batch %s to %s",
                        batch_start,
                        batch_end,
                    )
                    completed += 1

        logger.info(
            "Completed download of %s trades: %d records retrieved",
            symbol,
            len(all_data),
        )

        # Save all data if requested and not already saved by batch
        if all_data and not save_progress:
            self._save_data(
                data=all_data,
                symbol=symbol,
                data_type="trades",
                start_time=start_time_dt,
                end_time=end_time_dt,
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
        max_iterations = 100  # Safety limit for iterations
        # For trades, we need to use historical_trades with fromId
        # First, get the trade ID close to our start time
        # Convert times to milliseconds
        start_ms = int(start_time.timestamp() * MILLISECONDS_IN_SECOND)
        end_ms = int(end_time.timestamp() * MILLISECONDS_IN_SECOND)

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
        iteration_count = 0
        while iteration_count < max_iterations:
            iteration_count += 1
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
                if start_ms
                <= int(t.time.timestamp() * MILLISECONDS_IN_SECOND)
                <= end_ms
            ]

            all_trades.extend(valid_trades)

            # Check if we've reached the end time
            last_trade_time = int(batch[-1].time.timestamp() * MILLISECONDS_IN_SECOND)
            if last_trade_time > end_ms:
                break

            # Safety check for tests - if from_id doesn't change, we're in a loop
            next_from_id = batch[-1].id + 1
            if next_from_id == from_id:
                # We're not making progress, likely in a test with mocked data
                logger.warning(
                    "Trade ID not advancing, breaking loop at iteration %d",
                    iteration_count,
                )
                break

            # Update from_id for next iteration
            from_id = next_from_id

            # Avoid rate limiting
            time.sleep(0.1)

        # Check if we hit the max iteration limit
        if iteration_count >= max_iterations:
            logger.warning(
                "Reached maximum iteration limit (%d) when downloading trades",
                max_iterations,
            )

        return all_trades

    def download_multiple_symbols(
        self,
        config: DownloadBatchConfigSchema,
        symbols: list[str],
    ) -> dict[str, Path]:  # Fix return type
        """
        Download data for multiple symbols with the same configuration.

        Args:
            config: Download configuration
            symbols: List of symbols to download

        Returns:
            Dictionary of symbol to file path
        """
        results: dict[str, Path] = {}
        logger.info(
            "Starting download for %d symbols with interval %s",
            len(symbols),
            config.interval,
        )

        for i, symbol in enumerate(symbols):
            try:
                logger.info(
                    "Processing symbol %d/%d: %s",
                    i + 1,
                    len(symbols),
                    symbol,
                )

                if config.interval:  # Klines
                    data = self.download_klines(
                        symbol=symbol,
                        interval=config.interval,
                        start_time=config.start_time,
                        end_time=config.end_time,
                        batch_size=config.batch_size,
                        max_workers=config.max_workers,
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
                            output_dir=config.output_dir,
                        )
                        results[symbol] = filepath
                        logger.info(
                            "Downloaded %d records for %s",
                            len(data),
                            symbol,
                        )

            except Exception:
                logger.exception("Error downloading data for %s", symbol)

        logger.info(
            "Completed download for %d/%d symbols",
            len(results),
            len(symbols),
        )
        return results

    def download_all_symbols(  # noqa: C901
        self,
        interval: str,
        start_time: str | datetime,
        end_time: None | str | datetime = None,
        quote_asset: None | str = None,
        min_volume: None | float = None,
        batch_size: None | int = None,
        max_workers: None | int = None,
        output_dir: None | Path = None,
    ) -> dict[str, Path]:  # Fix return type
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
            output_dir: Directory to save data

        Returns:
            Dictionary of symbol to file path
        """
        # Get exchange information to find available symbols
        logger.info("Fetching exchange information...")
        exchange_info = self.client.get_exchange_info()
        all_symbols = exchange_info.get("symbols", [])
        logger.info("Found %d symbols on exchange", len(all_symbols))

        # Filter symbols
        filtered_symbols = []

        # Get 24h ticker data for volume filtering if needed
        tickers = None
        if min_volume:
            logger.info("Fetching 24h ticker data for volume filtering...")
            tickers = self.client.get_all_tickers()
            # Create a lookup dictionary
            ticker_map = {t.symbol: t for t in tickers}
            logger.info("Retrieved ticker data for %d symbols", len(ticker_map))

        logger.info("Filtering symbols...")
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

        filter_desc = ""
        if quote_asset or min_volume:
            filter_desc = f"(quote_asset={quote_asset}, min_volume={min_volume})"

        logger.info(
            "Filtered to %d symbols matching criteria %s",
            len(filtered_symbols),
            filter_desc,
        )

        # Process start and end times for config
        processed_start_time = (
            start_time
            if isinstance(start_time, datetime)
            else dateparser.parse(start_time)
        )
        if not processed_start_time:
            raise ValueError(f"Could not parse start_time: {start_time}")

        # Handle end_time with proper type checking
        processed_end_time: datetime
        if end_time is None:
            processed_end_time = utc_now()
        elif isinstance(end_time, datetime):
            processed_end_time = end_time
        else:
            parsed_end_time = dateparser.parse(end_time)
            if not parsed_end_time:
                raise ValueError(f"Could not parse end_time: {end_time}")
            processed_end_time = parsed_end_time

        # Create download config
        config = DownloadBatchConfigSchema(
            symbol="",  # Will be set per download
            interval=interval,
            start_time=processed_start_time,
            end_time=processed_end_time,
            batch_size=batch_size or self.batch_size,
            max_workers=max_workers or self.max_workers,
            output_dir=output_dir or self.output_dir,
        )

        # Download data for filtered symbols
        return self.download_multiple_symbols(config, filtered_symbols)
