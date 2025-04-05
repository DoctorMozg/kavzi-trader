"""
Binance Historical Data Client.

This module provides a specialized client for downloading large amounts
of historical data from Binance efficiently, with support
for batching, parallelization, and rate limiting.
"""

import logging
from datetime import datetime

import dateparser

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.binance.historical.batch import (
    DownloadBatchConfigSchema,
    SymbolicDownloadBatchConfigSchema,
)
from kavzi_trader.api.binance.historical.downloaders.klines import KlinesDownloader
from kavzi_trader.api.binance.historical.downloaders.trades import TradesDownloader
from kavzi_trader.api.common.models import CandlestickSchema, TradeSchema
from kavzi_trader.commons.time_utility import utc_now

logger = logging.getLogger(__name__)


class BinanceHistoricalDataClient:
    """
    Client for downloading large amounts of historical data from Binance efficiently.

    This client extends the standard BinanceClient with specialized methods for
    batch downloading and processing historical data with:
    - Parallel downloads using asyncio
    - Smart batching to maximize throughput
    - Automatic rate limiting
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
        """
        self.client = BinanceClient(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            timeout=timeout,
        )
        self.max_workers = max_workers
        self.batch_size = batch_size

        # Initialize specialized downloaders
        self.klines_downloader = KlinesDownloader(self.client)
        self.trades_downloader = TradesDownloader(self.client)

    async def download_klines(
        self,
        config: SymbolicDownloadBatchConfigSchema | None = None,
        symbol: str = "",
        interval: str = "",
        start_time: str | datetime | None = None,
        end_time: str | datetime | None = None,
    ) -> list[CandlestickSchema]:
        """
        Download historical klines (candlestick) data.

        Args:
            config: Configuration for the download batch
                (optional, overrides other params)
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            interval: Kline interval (e.g., "1m", "1h", "1d")
            start_time: Start time for the download (string or datetime)
            end_time: End time for the download (string or datetime, defaults to now)

        Returns:
            List of candlestick data
        """
        if config is None:
            # Create config from individual parameters
            config = SymbolicDownloadBatchConfigSchema(
                symbol=symbol,
                interval=interval,
                start_time=self._parse_time(start_time)
                if start_time is not None
                else utc_now(),
                end_time=self._parse_time(end_time)
                if end_time is not None
                else utc_now(),
                batch_size=self.batch_size,
                max_workers=self.max_workers,
            )

        return await self.klines_downloader.download(config=config)

    async def download_trades(
        self,
        config: SymbolicDownloadBatchConfigSchema | None = None,
        symbol: str = "",
        start_time: str | datetime | None = None,
        end_time: str | datetime | None = None,
    ) -> list[TradeSchema]:
        """
        Download historical trades data.

        Args:
            config: Configuration for the download batch
                (optional, overrides other params)
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            start_time: Start time for the download (string or datetime)
            end_time: End time for the download (string or datetime, defaults to now)

        Returns:
            List of trade data
        """
        if config is None:
            # Create config from individual parameters
            config = SymbolicDownloadBatchConfigSchema(
                symbol=symbol,
                # interval intentionally empty for trades
                start_time=self._parse_time(start_time)
                if start_time is not None
                else utc_now(),
                end_time=self._parse_time(end_time)
                if end_time is not None
                else utc_now(),
                max_workers=self.max_workers,
                batch_size=self.batch_size,
            )

        return await self.trades_downloader.download(config=config)

    async def download_multiple_symbols(
        self,
        config: DownloadBatchConfigSchema,
        symbols: list[str],
    ) -> dict[str, bool]:
        """
        Download data for multiple symbols with the same configuration.

        Args:
            config: Base download configuration (without symbol)
            symbols: List of symbols to download

        Returns:
            Dictionary of symbol to success status
        """
        results: dict[str, bool] = {}
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

                # Create a symbol-specific config
                symbol_config = SymbolicDownloadBatchConfigSchema(
                    symbol=symbol,
                    interval=config.interval,
                    start_time=config.start_time,
                    end_time=config.end_time,
                    batch_size=config.batch_size,
                    max_workers=config.max_workers,
                )

                if config.interval:  # Klines
                    data = await self.download_klines(config=symbol_config)

                    # Record the result
                    if data:
                        results[symbol] = True
                        logger.info(
                            "Downloaded %d records for %s",
                            len(data),
                            symbol,
                        )

            except Exception:
                logger.exception("Error downloading data for %s", symbol)
                results[symbol] = False

        logger.info(
            "Completed download for %d/%d symbols",
            sum(1 for success in results.values() if success),
            len(symbols),
        )
        return results

    async def download_all_symbols(
        self,
        config: DownloadBatchConfigSchema | None = None,
        interval: str = "",
        start_time: str | datetime | None = None,
        end_time: str | datetime | None = None,
        quote_asset: str | None = None,
        min_volume: float | None = None,
    ) -> dict[str, bool]:
        """
        Download data for all available symbols matching criteria.

        Args:
            config: Configuration for the download batch
                (optional, overrides other params)
            interval: Kline interval (e.g., "1m", "1h", "1d")
            start_time: Start time for the download
            end_time: End time for the download (defaults to now)
            quote_asset: Filter symbols by quote asset (e.g., "USDT")
            min_volume: Minimum 24h volume in USD

        Returns:
            Dictionary of symbol to success status
        """
        # Create or use config
        if config is None:
            # Process inputs for config
            processed_start_time = (
                self._parse_time(start_time) if start_time else utc_now()
            )
            processed_end_time = self._parse_time(end_time) if end_time else utc_now()

            config = DownloadBatchConfigSchema(
                interval=interval,
                start_time=processed_start_time,
                end_time=processed_end_time,
                batch_size=self.batch_size,
                max_workers=self.max_workers,
            )

        # Get filtered symbols
        filtered_symbols = await self.get_filtered_symbols(quote_asset, min_volume)

        # Download data for filtered symbols
        return await self.download_multiple_symbols(config, filtered_symbols)

    async def get_filtered_symbols(
        self,
        quote_asset: str | None = None,
        min_volume: float | None = None,
    ) -> list[str]:
        """
        Get filtered symbols based on criteria.

        Args:
            quote_asset: Filter symbols by quote asset (e.g., "USDT")
            min_volume: Minimum 24h volume in USD

        Returns:
            List of filtered symbol strings
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

        return filtered_symbols

    def _parse_time(self, time_value: str | datetime | None) -> datetime:
        """
        Parse a time value into a datetime object.

        Args:
            time_value: Time value to parse, can be string or datetime

        Returns:
            Datetime object
        """
        if time_value is None:
            return utc_now()

        if isinstance(time_value, datetime):
            return time_value

        parsed_time = dateparser.parse(time_value)
        if not parsed_time:
            raise ValueError(f"Could not parse time: {time_value}")

        return parsed_time
