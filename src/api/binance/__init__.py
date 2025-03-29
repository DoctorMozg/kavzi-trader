"""
Binance API connector.

This module provides an implementation of the Binance API for the trading system.
"""

from src.api.binance.client import BinanceClient
from src.api.binance.constants import KLINE_INTERVALS
from src.api.binance.historical import BinanceHistoricalDataClient
from src.api.binance.websocket import BinanceWebsocketClient

__all__ = [
    "BinanceClient",
    "BinanceHistoricalDataClient",
    "BinanceWebsocketClient",
    "KLINE_INTERVALS",
]
