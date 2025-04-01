"""
Binance Historical Data Client.

This module provides a specialized client for downloading large amounts
of historical data from Binance efficiently, with support
for batching, parallelization, and rate limiting.
"""

import logging
from datetime import datetime
from pathlib import Path

import dateparser

from src.api.binance.client import BinanceClient
from src.api.binance.historical.batch import DownloadBatchConfigSchema
from src.api.binance.historical.downloaders.klines import KlinesDownloader
from src.api.binance.historical.downloaders.trades import TradesDownloader
from src.api.common.models import CandlestickSchema, TradeSchema
from src.commons.time_utility import utc_now

logger = logging.getLogger(__name__)


class BinanceHistoricalDataClient:
    """
    Client for downloading large amounts of historical data from Binance efficiently.

    This client extends the standard BinanceClient with specialized methods for
    batch downloading and processing historical data with:
    - Parallel downloads using asyncio
    - Smart batching to maximize throughput
    - Automatic rate limiting
    - CSV output format
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
        output_dir: Path = Path("./data"),
        proxies: dict[str, str] | None = None,
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

        # Initialize specialized downloaders
        self.klines_downloader = KlinesDownloader(self.client)
        self.trades_downloader = TradesDownloader(self.client)

    async def download_klines(
        self,
        symbol: str,
        interval: str,
        start_time: str | datetime,
        end_time: str | datetime | None = None,
        batch_size: int | None = None,
        max_workers: int | None = None,
        output_dir: Path | None = None,
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
            output_dir: Directory to save data (defaults to self.output_dir)
            save_progress: Whether to save each batch as it completes

        Returns:
            List of candlestick data
        """
        return await self.klines_downloader.download(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size or self.batch_size,
            max_workers=max_workers or self.max_workers,
            output_dir=output_dir or self.output_dir,
            save_progress=save_progress,
        )

    async def download_trades(
        self,
        symbol: str,
        start_time: str | datetime,
        end_time: str | datetime | None = None,
        max_workers: int | None = None,
        output_dir: Path | None = None,
        save_progress: bool = True,
    ) -> list[TradeSchema]:
        """
        Download historical trades data.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            start_time: Start time for the download (string or datetime)
            end_time: End time for the download (string or datetime, defaults to now)
            max_workers: Maximum number of concurrent workers
            (defaults to self.max_workers)
            output_dir: Directory to save data (defaults to self.output_dir)
            save_progress: Whether to save each batch as it completes

        Returns:
            List of trade data
        """
        return await self.trades_downloader.download(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            max_workers=max_workers or self.max_workers,
            output_dir=output_dir or self.output_dir,
            save_progress=save_progress,
        )

    async def download_multiple_symbols(
        self,
        config: DownloadBatchConfigSchema,
        symbols: list[str],
    ) -> dict[str, Path]:
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
                    data = await self.download_klines(
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
                        filepath = self.klines_downloader.data_saver.save_data(
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

    async def download_all_symbols(  # noqa: C901,PLR0912
        self,
        interval: str,
        start_time: str | datetime,
        end_time: str | datetime | None = None,
        quote_asset: str | None = None,
        min_volume: float | None = None,
        batch_size: int | None = None,
        max_workers: int | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, Path]:
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
        exchange_info = await self.client.get_exchange_info()
        all_symbols = exchange_info.get("symbols", [])
        logger.info("Found %d symbols on exchange", len(all_symbols))

        # Filter symbols
        filtered_symbols = []

        # Get 24h ticker data for volume filtering if needed
        tickers = None
        if min_volume:
            logger.info("Fetching 24h ticker data for volume filtering...")
            tickers = await self.client.get_all_tickers()
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
        if isinstance(start_time, str):
            processed_start_time = dateparser.parse(start_time)
            if not processed_start_time:
                raise ValueError(f"Could not parse start_time: {start_time}")
        else:
            processed_start_time = start_time

        # Handle end_time with proper type checking
        if end_time is None:
            processed_end_time = utc_now()
        elif isinstance(end_time, str):
            parsed_end_time = dateparser.parse(end_time)
            if not parsed_end_time:
                raise ValueError(f"Could not parse end_time: {end_time}")
            processed_end_time = parsed_end_time
        else:
            processed_end_time = end_time

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
        return await self.download_multiple_symbols(config, filtered_symbols)
