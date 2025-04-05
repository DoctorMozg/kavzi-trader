"""
Binance Historical Data Client Package.

This package provides specialized clients for downloading large amounts
of historical data from Binance efficiently.
"""

from kavzi_trader.api.binance.historical.batch import DownloadBatchConfigSchema
from kavzi_trader.api.binance.historical.client import BinanceHistoricalDataClient

__all__ = ["BinanceHistoricalDataClient", "DownloadBatchConfigSchema"]
