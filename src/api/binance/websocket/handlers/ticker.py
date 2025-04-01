"""
Ticker stream handler for Binance WebSocket.

This module provides a handler for ticker WebSocket streams.
"""

import logging
from collections.abc import Callable
from typing import Any, Awaitable

from src.api.binance.schemas.data_dicts import TickerData
from src.api.binance.websocket.handlers.base import BaseStreamHandler
from src.api.binance.websocket.stream_manager import StreamManager

logger = logging.getLogger(__name__)


class TickerStreamHandler(BaseStreamHandler[TickerData]):
    """Handler for ticker WebSocket streams."""

    def __init__(self, stream_manager: StreamManager) -> None:
        """Initialize the TickerStreamHandler."""
        super().__init__(stream_manager)

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[TickerData], Awaitable[None]],
        **kwargs: Any,  # noqa: ARG002,ANN401
    ) -> str:
        """
        Subscribe to 24hr ticker updates stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for ticker data
            **kwargs: Additional parameters (not used for ticker streams)

        Returns:
            Stream name
        """
        symbol = symbol.lower()
        stream_name = f"{symbol}@ticker"

        return await self._start_socket(
            socket_func=self.stream_manager.bsm.symbol_ticker_socket,
            stream_name=stream_name,
            callback=callback,
            symbol=symbol.upper(),
        )
