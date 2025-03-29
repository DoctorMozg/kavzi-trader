"""
Service for downloading historical market data.

This module provides services for downloading various types of historical
market data from different sources.
"""

from datetime import datetime
from pathlib import Path

import click

from src.api.binance.historical.batch import DownloadBatchConfigSchema
from src.api.binance.historical.client import BinanceHistoricalDataClient
from src.api.common.models import CandlestickSchema, TradeSchema
from src.commons.logging import get_logger
from src.commons.time_utility import utc_now

# Initialize logger
logger = get_logger(name=__name__)


class HistoricalDownloadService:
    """
    Service for downloading historical market data.
    """

    def __init__(self, client: BinanceHistoricalDataClient) -> None:
        """
        Initialize the download service.

        Args:
            client: The historical data client to use for downloads
        """
        self.client = client

    def download_klines(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime | None = None,
        batch_size: int = 1000,
        max_workers: int = 4,
        output_dir: Path = Path("./data"),
        save_progress: bool = True,
    ) -> list[CandlestickSchema]:
        """
        Download historical klines (candlestick) data.

        Args:
            symbol: Trading pair symbol (e.g., BTCUSDT)
            interval: Kline interval (e.g., 1m, 5m, 15m, 1h, 4h, 1d)
            start_time: Start time for historical data
            end_time: End time for historical data (optional)
            batch_size: Size of each download batch
            max_workers: Maximum number of concurrent download workers
            output_dir: Directory to save downloaded data
            save_progress: Whether to save each batch as it completes

        Returns:
            List of downloaded kline data
        """
        logger.info(
            "Downloading %s %s data from %s to %s",
            symbol,
            interval,
            start_time,
            end_time or "now",
        )

        try:
            data = self.client.download_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                batch_size=batch_size,
                max_workers=max_workers,
                output_dir=output_dir,
                save_progress=save_progress,
            )

            logger.info(
                "Successfully downloaded %d records for %s %s",
                len(data),
                symbol,
                interval,
            )
        except Exception as e:
            logger.exception("Error downloading historical klines data")
            raise click.ClickException(f"Failed to download data: {e!s}") from e
        else:
            return data

    def download_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime | None = None,
        max_workers: int = 4,
        output_dir: Path = Path("./data"),
        save_progress: bool = True,
    ) -> list[TradeSchema]:
        """
        Download historical trades data.

        Args:
            symbol: Trading pair symbol (e.g., BTCUSDT)
            start_time: Start time for historical data
            end_time: End time for historical data (optional)
            max_workers: Maximum number of concurrent download workers
            output_dir: Directory to save downloaded data
            save_progress: Whether to save each batch as it completes

        Returns:
            List of downloaded trades data
        """
        logger.info(
            "Downloading %s trades data from %s to %s",
            symbol,
            start_time,
            end_time or "now",
        )

        try:
            data = self.client.download_trades(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                max_workers=max_workers,
                output_dir=output_dir,
                save_progress=save_progress,
            )

            logger.info(
                "Successfully downloaded %d trades for %s",
                len(data),
                symbol,
            )
        except Exception as e:
            logger.exception("Error downloading trades data")
            raise click.ClickException(f"Failed to download trades: {e!s}") from e
        else:
            return data

    def download_multiple_symbols(
        self,
        symbols: list[str],
        interval: str,
        start_time: datetime,
        end_time: datetime | None = None,
        batch_size: int = 1000,
        max_workers: int = 4,
        output_dir: Path = Path("./data"),
    ) -> dict[str, Path]:
        """
        Download historical klines data for multiple symbols.

        Args:
            symbols: List of trading pair symbols
            interval: Kline interval
            start_time: Start time for historical data
            end_time: End time for historical data (optional)
            batch_size: Size of each download batch
            max_workers: Maximum number of concurrent download workers
            output_dir: Directory to save downloaded data

        Returns:
            List of successfully downloaded symbols
        """
        logger.info(
            "Downloading data for %d symbols with interval %s from %s to %s",
            len(symbols),
            interval,
            start_time,
            end_time or "now",
        )

        # Create download config
        download_config = DownloadBatchConfigSchema(
            symbol="",  # Will be set per download
            interval=interval,
            start_time=start_time,
            end_time=end_time or utc_now(),
            batch_size=batch_size,
            max_workers=max_workers,
            output_dir=output_dir,
        )

        try:
            results = self.client.download_multiple_symbols(
                config=download_config,
                symbols=symbols,
            )

            logger.info(
                "Successfully downloaded data for %d/%d symbols",
                len(results),
                len(symbols),
            )
        except Exception as e:
            logger.exception("Error downloading historical data for multiple symbols")
            raise click.ClickException(f"Failed to download data: {e!s}") from e
        else:
            return results

    def download_all_symbols(
        self,
        interval: str,
        start_time: datetime,
        end_time: datetime | None = None,
        quote_asset: str = "USDT",
        min_volume: float | None = None,
        batch_size: int = 1000,
        max_workers: int = 4,
        output_dir: Path = Path("./data"),
    ) -> dict[str, Path]:
        """
        Download historical klines data for all available symbols matching criteria.

        Args:
            interval: Kline interval
            start_time: Start time for historical data
            end_time: End time for historical data (optional)
            quote_asset: Filter symbols by quote asset (e.g., USDT, BTC)
            min_volume: Minimum 24h volume in USD
            batch_size: Size of each download batch
            max_workers: Maximum number of concurrent download workers
            output_dir: Directory to save downloaded data

        Returns:
            List of successfully downloaded symbols
        """
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
            results = self.client.download_all_symbols(
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                quote_asset=quote_asset,
                min_volume=min_volume,
                batch_size=batch_size,
                max_workers=max_workers,
                output_dir=output_dir,
            )

            logger.info("Successfully downloaded data for %d symbols", len(results))
        except Exception as e:
            logger.exception("Error downloading historical data for all symbols")
            raise click.ClickException(f"Failed to download data: {e!s}") from e
        else:
            return results
