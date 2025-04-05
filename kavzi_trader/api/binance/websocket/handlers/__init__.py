"""
WebSocket stream handlers for Binance.

This package contains specialized handlers for different types of WebSocket streams.
"""

from kavzi_trader.api.binance.websocket.handlers.base import BaseStreamHandler
from kavzi_trader.api.binance.websocket.handlers.depth import DepthStreamHandler
from kavzi_trader.api.binance.websocket.handlers.klines import KlineStreamHandler
from kavzi_trader.api.binance.websocket.handlers.ticker import TickerStreamHandler
from kavzi_trader.api.binance.websocket.handlers.trades import TradeStreamHandler
from kavzi_trader.api.binance.websocket.handlers.user_data import UserDataStreamHandler

__all__ = [
    "BaseStreamHandler",
    "KlineStreamHandler",
    "TickerStreamHandler",
    "TradeStreamHandler",
    "DepthStreamHandler",
    "UserDataStreamHandler",
]
