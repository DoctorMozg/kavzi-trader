"""
Service for downloading historical market data.

This module provides services for downloading various types of historical
market data from different sources and storing them in the database.
"""

import logging
from typing import Any

import click
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.binance.historical.batch import (
    DownloadBatchConfigSchema,
    SymbolicDownloadBatchConfigSchema,
)
from src.api.binance.historical.client import BinanceHistoricalDataClient
from src.api.common.models import CandlestickSchema, TradeSchema
from src.data.storage.repos import MarketDataRepository, TradeDataRepository

# Initialize logger
logger = logging.getLogger(__name__)


class HistoricalDownloadService:
    """
    Service for downloading historical market data and storing it in the database.
    """

    def __init__(
        self,
        client: BinanceHistoricalDataClient,
        db_session: AsyncSession,
    ) -> None:
        """
        Initialize the download service.

        Args:
            client: The historical data client to use for downloads
            db_session: SQLAlchemy async session for database operations
        """
        self.client = client
        self.market_data_repo = MarketDataRepository(db_session)
        self.trade_data_repo = TradeDataRepository(db_session)

    async def download_klines(
        self,
        config: SymbolicDownloadBatchConfigSchema,
    ) -> list[CandlestickSchema]:
        """
        Download historical klines (candlestick) data and save to database.

        Args:
            config: Configuration for the download batch with symbol

        Returns:
            List of downloaded kline data
        """
        logger.info(
            "Downloading %s %s data from %s to %s",
            config.symbol,
            config.interval,
            config.start_time,
            config.end_time or "now",
        )

        try:
            data = await self.client.download_klines(config=config)

            logger.info(
                "Successfully downloaded %d records for %s %s",
                len(data),
                config.symbol,
                config.interval,
            )

            # Always save data to database
            await self.market_data_repo.save_candlesticks(
                candlesticks=data,
                symbol=config.symbol,
                interval=config.interval,
                batch_size=config.batch_size,
            )

        except Exception as e:
            logger.exception("Error downloading historical klines data")
            raise click.ClickException(f"Failed to download data: {e!s}") from e
        else:
            return data

    async def download_trades(
        self,
        config: SymbolicDownloadBatchConfigSchema,
    ) -> list[TradeSchema]:
        """
        Download historical trades data and save to database.

        Args:
            config: Configuration for the download batch with symbol

        Returns:
            List of downloaded trades data
        """
        logger.info(
            "Downloading %s trades data from %s to %s",
            config.symbol,
            config.start_time,
            config.end_time or "now",
        )

        try:
            data = await self.client.download_trades(config=config)

            logger.info(
                "Successfully downloaded %d trades for %s",
                len(data),
                config.symbol,
            )

            # Always save trade data to database
            await self.trade_data_repo.save_trades(
                trades=data,
                symbol=config.symbol,
                batch_size=1000,
            )

        except Exception as e:
            logger.exception("Error downloading trades data")
            raise click.ClickException(f"Failed to download trades: {e!s}") from e
        else:
            return data

    async def download_multiple_symbols(
        self,
        symbols: list[str],
        base_config: DownloadBatchConfigSchema,
    ) -> dict[str, Any]:
        """
        Download historical klines data for multiple symbols and save to database.

        Args:
            symbols: List of trading pair symbols
            base_config: Base configuration for the download batch (without symbol)

        Returns:
            Dictionary with symbol keys and success status values
        """
        logger.info(
            "Downloading data for %d symbols with interval %s from %s to %s",
            len(symbols),
            base_config.interval,
            base_config.start_time,
            base_config.end_time or "now",
        )

        results = {}

        try:
            for symbol in symbols:
                try:
                    logger.info("Processing symbol: %s", symbol)

                    # Create a symbol-specific config using clone
                    symbol_config = SymbolicDownloadBatchConfigSchema(
                        symbol=symbol,
                        interval=base_config.interval,
                        start_time=base_config.start_time,
                        end_time=base_config.end_time,
                        batch_size=base_config.batch_size,
                        max_workers=base_config.max_workers,
                    )

                    data = await self.download_klines(config=symbol_config)

                    if data:
                        results[symbol] = True
                except Exception:
                    logger.exception("Error processing symbol %s", symbol)
                    results[symbol] = False

            logger.info(
                "Successfully downloaded data for %d/%d symbols",
                sum(1 for success in results.values() if success),
                len(symbols),
            )
        except Exception as e:
            logger.exception("Error downloading historical data for multiple symbols")
            raise click.ClickException(f"Failed to download data: {e!s}") from e
        else:
            return results

    async def download_trades_for_multiple_symbols(
        self,
        symbols: list[str],
        base_config: DownloadBatchConfigSchema,
    ) -> dict[str, Any]:
        """
        Download historical trades data for multiple symbols and save to database.

        Args:
            symbols: List of trading pair symbols
            base_config: Base configuration for the download batch (without symbol)

        Returns:
            Dictionary with symbol keys and success status values
        """
        logger.info(
            "Downloading trades data for %d symbols from %s to %s",
            len(symbols),
            base_config.start_time,
            base_config.end_time or "now",
        )

        results = {}

        try:
            for symbol in symbols:
                try:
                    logger.info("Processing symbol trades: %s", symbol)

                    # Create a symbol-specific config using clone
                    symbol_config = SymbolicDownloadBatchConfigSchema(
                        symbol=symbol,
                        start_time=base_config.start_time,
                        end_time=base_config.end_time,
                        max_workers=base_config.max_workers,
                    )

                    data = await self.download_trades(config=symbol_config)

                    if data:
                        results[symbol] = True
                except Exception:
                    logger.exception("Error processing symbol trades %s", symbol)
                    results[symbol] = False

            logger.info(
                "Successfully downloaded trades data for %d/%d symbols",
                sum(1 for success in results.values() if success),
                len(symbols),
            )
        except Exception as e:
            logger.exception("Error downloading trades data for multiple symbols")
            raise click.ClickException(f"Failed to download trades data: {e!s}") from e
        else:
            return results

    async def download_all_symbols(
        self,
        base_config: DownloadBatchConfigSchema,
        quote_asset: str = "USDT",
        min_volume: float | None = None,
    ) -> dict[str, Any]:
        """
        Download historical klines data for all available symbols matching criteria
        and save to database.

        Args:
            base_config: Base configuration for the download batch (without symbol)
            quote_asset: Filter symbols by quote asset (e.g., USDT, BTC)
            min_volume: Minimum 24h volume in USD

        Returns:
            Dictionary with symbol keys and success status values
        """
        filter_desc = f"quote_asset={quote_asset}"
        if min_volume:
            filter_desc += f", min_volume={min_volume}"

        logger.info(
            "Downloading data for all symbols matching criteria (%s) with interval %s"
            " from %s to %s",
            filter_desc,
            base_config.interval,
            base_config.start_time,
            base_config.end_time or "now",
        )

        results = {}

        try:
            # Get filtered symbols first
            filtered_symbols = await self.client.get_filtered_symbols(
                quote_asset=quote_asset,
                min_volume=min_volume,
            )

            logger.info("Found %d symbols matching criteria", len(filtered_symbols))

            # Process each symbol
            for symbol in filtered_symbols:
                try:
                    logger.info("Processing symbol: %s", symbol)

                    # Create a symbol-specific config using clone
                    symbol_config = SymbolicDownloadBatchConfigSchema(
                        symbol=symbol,
                        interval=base_config.interval,
                        start_time=base_config.start_time,
                        end_time=base_config.end_time,
                        batch_size=base_config.batch_size,
                        max_workers=base_config.max_workers,
                    )

                    data = await self.download_klines(config=symbol_config)

                    if data:
                        results[symbol] = True
                except Exception:
                    logger.exception("Error processing symbol %s", symbol)
                    results[symbol] = False

            logger.info(
                "Successfully downloaded data for %d symbols",
                sum(1 for success in results.values() if success),
            )
        except Exception as e:
            logger.exception("Error downloading historical data for all symbols")
            raise click.ClickException(f"Failed to download data: {e!s}") from e
        else:
            return results

    async def download_all_trades(
        self,
        base_config: DownloadBatchConfigSchema,
        quote_asset: str = "USDT",
        min_volume: float | None = None,
    ) -> dict[str, Any]:
        """
        Download historical trades data for all available symbols matching criteria
        and save to database.

        Args:
            base_config: Base configuration for the download batch (without symbol)
            quote_asset: Filter symbols by quote asset (e.g., USDT, BTC)
            min_volume: Minimum 24h volume in USD

        Returns:
            Dictionary with symbol keys and success status values
        """
        filter_desc = f"quote_asset={quote_asset}"
        if min_volume:
            filter_desc += f", min_volume={min_volume}"

        logger.info(
            "Downloading trades data for all symbols matching criteria (%s)"
            " from %s to %s",
            filter_desc,
            base_config.start_time,
            base_config.end_time or "now",
        )

        results = {}

        try:
            # Get filtered symbols first
            filtered_symbols = await self.client.get_filtered_symbols(
                quote_asset=quote_asset,
                min_volume=min_volume,
            )

            logger.info("Found %d symbols matching criteria", len(filtered_symbols))

            # Process each symbol
            for symbol in filtered_symbols:
                try:
                    logger.info("Processing symbol trades: %s", symbol)

                    # Create a symbol-specific config using clone
                    symbol_config = SymbolicDownloadBatchConfigSchema(
                        symbol=symbol,
                        start_time=base_config.start_time,
                        end_time=base_config.end_time,
                        max_workers=base_config.max_workers,
                    )

                    data = await self.download_trades(config=symbol_config)

                    if data:
                        results[symbol] = True
                except Exception:
                    logger.exception("Error processing symbol trades %s", symbol)
                    results[symbol] = False

            logger.info(
                "Successfully downloaded trades data for %d symbols",
                sum(1 for success in results.values() if success),
            )
        except Exception as e:
            logger.exception("Error downloading trades data for all symbols")
            raise click.ClickException(f"Failed to download trades data: {e!s}") from e
        else:
            return results
