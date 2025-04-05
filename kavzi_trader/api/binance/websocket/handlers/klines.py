"""
Kline stream handler for Binance WebSocket.

This module provides a handler for kline/candlestick WebSocket streams.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.binance.schemas.data_dicts import KlineData
from kavzi_trader.api.binance.websocket.handlers.base import BaseStreamHandler
from kavzi_trader.api.binance.websocket.stream_manager import StreamManager

logger = logging.getLogger(__name__)


class KlineStreamHandler(BaseStreamHandler[KlineData]):
    """Handler for kline/candlestick WebSocket streams."""

    def __init__(self, stream_manager: StreamManager) -> None:
        """Initialize the KlineStreamHandler."""
        super().__init__(stream_manager)

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[KlineData], Awaitable[None]],
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        """
        Subscribe to kline/candlestick data stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for kline data
            **kwargs: Additional parameters, including:
                - interval: Kline interval (e.g., "1m", "1h", "1d")

        Returns:
            Stream name
        """
        interval = cast(str, kwargs.get("interval"))
        if not interval:
            raise ValueError("Interval is required for kline streams")

        if interval not in KLINE_INTERVALS:
            valid_intervals = ", ".join(KLINE_INTERVALS.keys())
            raise ValueError(
                f"Invalid interval: {interval}. Valid intervals: {valid_intervals}",
            )

        symbol = symbol.lower()
        stream_name = f"{symbol}@kline_{interval}"

        return await self._start_socket(
            socket_func=self.stream_manager.bsm.kline_socket,
            stream_name=stream_name,
            callback=callback,
            symbol=symbol.upper(),
            interval=interval,
        )
