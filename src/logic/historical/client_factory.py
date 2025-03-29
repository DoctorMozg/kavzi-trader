"""
Factory for creating historical data clients.

This module provides functionality for creating and configuring
historical data clients for different data sources.
"""

from pathlib import Path

from src.api.binance.historical.client import BinanceHistoricalDataClient
from src.commons.logging import get_logger

# Initialize logger
logger = get_logger(name=__name__)


class HistoricalClientFactory:
    """
    Factory for creating and configuring historical data clients.
    """

    @staticmethod
    def create_binance_client(
        api_key: str,
        api_secret: str,
        max_workers: int,
        batch_size: int,
        output_dir: Path,
    ) -> BinanceHistoricalDataClient:
        """
        Create and configure a Binance historical data client.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            max_workers: Maximum number of concurrent download workers
            batch_size: Size of each download batch
            output_dir: Directory to save downloaded data

        Returns:
            BinanceHistoricalDataClient: Configured client instance
        """
        logger.debug(
            "Creating Binance historical data client with max_workers=%d, "
            "batch_size=%d",
            max_workers,
            batch_size,
        )

        return BinanceHistoricalDataClient(
            api_key=api_key,
            api_secret=api_secret,
            max_workers=max_workers,
            batch_size=batch_size,
            output_dir=output_dir,
        )
