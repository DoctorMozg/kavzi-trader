"""
Trade stream handler for Binance WebSocket.

This module provides a handler for trade WebSocket streams.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.api.binance.schemas.data_dicts import TradeData
from src.api.binance.websocket.handlers.base import BaseStreamHandler
from src.api.binance.websocket.stream_manager import StreamManager

logger = logging.getLogger(__name__)


class TradeStreamHandler(BaseStreamHandler[TradeData]):
    """Handler for trade WebSocket streams."""

    def __init__(self, stream_manager: StreamManager) -> None:
        """Initialize the TradeStreamHandler."""
        super().__init__(stream_manager)

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[TradeData], Awaitable[None]],
        **kwargs: Any,  # noqa: ANN401, ARG002
    ) -> str:
        """
        Subscribe to trade updates stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for trade data
            **kwargs: Additional parameters (not used for trade streams)

        Returns:
            Stream name
        """
        symbol = symbol.lower()
        stream_name = f"{symbol}@trade"

        return await self._start_socket(
            socket_func=self.stream_manager.bsm.trade_socket,
            stream_name=stream_name,
            callback=callback,
            symbol=symbol.upper(),
        )
