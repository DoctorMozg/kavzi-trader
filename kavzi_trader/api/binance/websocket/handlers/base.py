"""
Base stream handler for Binance WebSocket streams.

This module provides a base class for handling different types of WebSocket streams.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from binance import ReconnectingWebsocket
from binance.exceptions import BinanceAPIException

from kavzi_trader.api.binance.websocket.stream_manager import StreamManager
from kavzi_trader.api.common.exceptions import APIError

logger = logging.getLogger(__name__)


class BaseStreamHandler[T](ABC):
    """
    Base class for WebSocket stream handlers.

    This abstract class provides common functionality for all stream handlers,
    including subscription management and error handling.
    """

    def __init__(self, stream_manager: StreamManager) -> None:
        """
        Initialize the BaseStreamHandler.

        Args:
            stream_manager: StreamManager instance for managing WebSocket connections
        """
        self.stream_manager = stream_manager

    @abstractmethod
    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[T], Awaitable[None]],
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        """
        Subscribe to a stream.

        Args:
            symbol: Trading pair symbol
            callback: Callback for stream data
            **kwargs: Additional parameters specific to the stream type

        Returns:
            Stream name
        """

    async def unsubscribe(self, stream_name: str) -> None:
        """
        Unsubscribe from a stream.

        Args:
            stream_name: Name of the stream to unsubscribe from
        """
        try:
            await self.stream_manager.unregister_stream(stream_name)
        except Exception as err:
            logger.exception("Error unsubscribing from stream")
            raise APIError(f"Error unsubscribing from stream: {err!s}") from err

    async def _start_socket(
        self,
        socket_func: Callable[..., ReconnectingWebsocket],
        stream_name: str,
        callback: Callable[[T], Awaitable[None]],
        symbol: str | None = None,
        interval: str | None = None,
        depth: int | None = None,
    ) -> str:
        """
        Start a WebSocket socket using the provided function.

        Args:
            socket_func: Function to start the socket
            stream_name: Name of the stream
            callback: Callback for stream data
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            interval: Kline interval (e.g., "1m", "1h", "1d")
            depth: Depth of the order book (5, 10, or 20)

        Returns:
            Stream name
        """
        # Ensure the WebSocket manager is running
        await self.stream_manager.start()

        # Store the callback
        self.stream_manager.add_stream_callback(stream_name, callback)  # type: ignore

        try:
            # Prepare arguments for the socket function
            # (library methods accept symbol/interval/depth, NOT callback)
            socket_args: dict[str, Any] = {}
            if symbol:
                socket_args["symbol"] = symbol
            if interval:
                socket_args["interval"] = interval
            if depth:
                socket_args["depth"] = depth

            # Get a ReconnectingWebsocket from the library
            socket = socket_func(**socket_args)

            # Register → connects, starts recv loop, tracks callback
            self.stream_manager.register_stream(
                stream_name=stream_name,
                socket=socket,
                callback=callback,  # type: ignore
            )

            logger.info("Subscribed to stream: %s", stream_name)
        except BinanceAPIException as err:
            logger.exception("Failed to subscribe to stream: %s", stream_name)
            raise APIError(f"Failed to subscribe to stream: {err!s}") from err
        else:
            return stream_name
