"""
Depth stream handler for Binance WebSocket.

This module provides a handler for order book depth WebSocket streams.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from kavzi_trader.api.binance.websocket.handlers.base import BaseStreamHandler

logger = logging.getLogger(__name__)


class DepthStreamHandler(BaseStreamHandler[dict[str, Any]]):
    """Handler for order book depth WebSocket streams."""

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        """
        Subscribe to order book depth stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for depth data
            **kwargs: Additional parameters, including:
                - depth: Depth of the order book (5, 10, or 20)

        Returns:
            Stream name
        """
        depth = kwargs.get("depth", 20)
        if depth not in (5, 10, 20):
            raise ValueError("Depth must be 5, 10, or 20")

        symbol = symbol.lower()
        stream_name = f"{symbol}@depth{depth}"

        return await self._start_socket(
            socket_func=self.stream_manager.bsm.depth_socket,
            stream_name=stream_name,
            callback=callback,
            symbol=symbol.upper(),
            depth=depth,
        )
