"""
Binance WebSocket client implementation.

This module provides a WebSocket client for real-time data from Binance.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, Union, cast

from binance.websocket.spot.websocket_client import SpotWebsocketClient

from src.api.binance.constants import (
    BINANCE_WS_TESTNET_URL,
    BINANCE_WS_URL,
    KLINE_INTERVALS,
)
from src.api.common.exceptions import APIError

logger = logging.getLogger(__name__)

# Type aliases for callback types
T = TypeVar("T", bound=dict[str, Any])


class MessageHandler(Protocol):
    """Protocol for handling WebSocket messages."""

    def __call__(self, message: dict[str, Any]) -> None: ...


class AsyncMessageHandler(Protocol):
    """Protocol for handling WebSocket messages asynchronously."""

    async def __call__(self, message: dict[str, Any]) -> None: ...


# Union type for both sync and async handlers
CallbackType = Union[MessageHandler, AsyncMessageHandler]


class BinanceWebsocketClient:
    """
    Binance WebSocket client for real-time market data.

    This class provides methods to stream market data from Binance using WebSockets.
    It wraps the python-binance library's WebSocketClient for easier integration.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        on_message: CallbackType | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_close: Callable[[], None] | None = None,
        error_callback: Callable[[Exception], None] | None = None,
    ):
        """
        Initialize Binance WebSocket client.

        Args:
            api_key: API key for authenticated streams
            api_secret: API secret for authenticated streams
            testnet: Whether to use the testnet
            on_message: Callback for received messages
            on_error: Callback for errors
            on_close: Callback for connection close
            error_callback: Alternative error callback
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.ws_url = BINANCE_WS_TESTNET_URL if testnet else BINANCE_WS_URL

        self.client = SpotWebsocketClient(
            stream_url=self.ws_url,
            on_message=self._on_message,
            on_close=self._on_close,
            on_error=self._on_error,
        )

        # Store active streams for management
        self.active_streams: set[str] = set()

        # User-provided callbacks
        self.on_message_callback = on_message
        self.on_error_callback = on_error or error_callback
        self.on_close_callback = on_close

        # Stream-specific callbacks
        self.stream_callbacks: dict[str, CallbackType] = {}

    def start(self) -> None:
        """Start the WebSocket connection."""
        try:
            self.client.start()
            logger.info("Binance WebSocket client started")
        except Exception as e:
            logger.exception("Failed to start Binance WebSocket client: %s", e)
            raise APIError(f"Failed to start WebSocket client: {e!s}")

    def stop(self) -> None:
        """Stop the WebSocket connection."""
        try:
            self.client.stop()
            self.active_streams.clear()
            logger.info("Binance WebSocket client stopped")
        except Exception as e:
            logger.exception("Failed to stop Binance WebSocket client: %s", e)
            raise APIError(f"Failed to stop WebSocket client: {e!s}")

    async def _process_message(self, stream: str, data: dict[str, Any]) -> None:
        """
        Process a message and route it to the appropriate callback.

        Args:
            stream: Stream name
            data: Message data
        """
        callback = self.stream_callbacks.get(stream)
        if callback:
            if asyncio.iscoroutinefunction(callback):
                # Async callback
                await cast(AsyncMessageHandler, callback)(data)
            else:
                # Sync callback
                cast(MessageHandler, callback)(data)

    def _on_message(self, message: dict[str, Any]) -> None:
        """
        Internal message handler.

        Processes the message and routes it to the appropriate callback.

        Args:
            message: Message received from WebSocket
        """
        try:
            # If message has a stream field, it's from a combined stream
            stream = message.get("stream")
            data = message.get("data", message)

            if stream and stream in self.stream_callbacks:
                # Call the specific callback for this stream
                asyncio.create_task(self._process_message(stream, data))

            # Always call the general callback if provided
            if self.on_message_callback:
                if asyncio.iscoroutinefunction(self.on_message_callback):
                    # Async callback
                    asyncio.create_task(
                        cast(AsyncMessageHandler, self.on_message_callback)(message),
                    )
                else:
                    # Sync callback
                    cast(MessageHandler, self.on_message_callback)(message)

            # Log debug information
            logger.debug("Received WebSocket message: %s", json.dumps(message)[:200])
        except Exception as e:
            logger.exception("Error processing WebSocket message: %s", e)
            self._on_error(e)

    def _on_error(self, error: Exception) -> None:
        """
        Internal error handler.

        Args:
            error: Error object
        """
        error_msg = str(error)
        logger.error("WebSocket error: %s", error_msg)
        if self.on_error_callback:
            self.on_error_callback(error)

    def _on_close(self) -> None:
        """Internal close handler."""
        logger.info("WebSocket connection closed")
        if self.on_close_callback:
            self.on_close_callback()

    async def subscribe_kline_stream(
        self,
        symbol: str,
        interval: str,
        callback: CallbackType,
    ) -> str:
        """
        Subscribe to kline/candlestick data stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            interval: Kline interval (e.g., "1m", "1h", "1d")
            callback: Callback for kline data

        Returns:
            Stream name
        """
        if interval not in KLINE_INTERVALS:
            valid_intervals = ", ".join(KLINE_INTERVALS.keys())
            raise ValueError(
                f"Invalid interval: {interval}. Valid intervals: {valid_intervals}",
            )

        symbol = symbol.lower()
        stream_name = f"{symbol}@kline_{interval}"

        self.stream_callbacks[stream_name] = callback

        await self._start_websocket()
        self.client.kline(
            symbol=symbol,
            interval=interval,
            id=1,
            callback=self._on_message,
        )
        self.active_streams.add(stream_name)
        logger.info("Subscribed to kline stream: %s", stream_name)

        return stream_name

    async def subscribe_ticker_stream(
        self,
        symbol: str,
        callback: CallbackType,
    ) -> str:
        """
        Subscribe to 24hr ticker updates stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for ticker data

        Returns:
            Stream name
        """
        symbol = symbol.lower()
        stream_name = f"{symbol}@ticker"

        self.stream_callbacks[stream_name] = callback

        await self._start_websocket()
        self.client.ticker(symbol=symbol, id=1, callback=self._on_message)
        self.active_streams.add(stream_name)
        logger.info("Subscribed to ticker stream: %s", stream_name)

        return stream_name

    async def _start_websocket(self) -> None:
        """Start the WebSocket connection if not already started."""
        if not self.is_connected():
            self.start()

    async def unsubscribe_stream(self, stream_name: str) -> None:
        """
        Unsubscribe from a stream.

        Args:
            stream_name: Name of the stream to unsubscribe from
        """
        if stream_name in self.active_streams:
            try:
                # Close the specific stream
                # The API doesn't provide a direct way to close a single stream
                # so we need to close all and reopen the ones we want to keep
                self.client.stop_socket(stream_name)
                self.active_streams.remove(stream_name)
                self.stream_callbacks.pop(stream_name, None)
                logger.info("Unsubscribed from stream: %s", stream_name)
            except Exception as e:
                logger.error("Failed to unsubscribe from stream %s: %s", stream_name, e)
                raise APIError(f"Failed to unsubscribe: {e!s}")

    async def unsubscribe_all_streams(self) -> None:
        """Unsubscribe from all streams."""
        try:
            self.stop()
            logger.info("Unsubscribed from all streams")
        except Exception as e:
            logger.error("Failed to unsubscribe from all streams: %s", e)
            raise APIError(f"Failed to unsubscribe: {e!s}")

    async def list_active_streams(self) -> list[str]:
        """
        List active streams.

        Returns:
            List of active stream names
        """
        return list(self.active_streams)

    def is_connected(self) -> bool:
        """
        Check if the WebSocket is connected.

        Returns:
            True if connected, False otherwise
        """
        return hasattr(self.client, "_conn") and self.client._conn is not None
