"""
Binance API connector.

This module provides an implementation of the Binance API for the trading system.
"""

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.binance.historical import BinanceHistoricalDataClient
from kavzi_trader.api.binance.websocket import BinanceWebsocketClient

__all__ = [
    "KLINE_INTERVALS",
    "BinanceClient",
    "BinanceHistoricalDataClient",
    "BinanceWebsocketClient",
]
