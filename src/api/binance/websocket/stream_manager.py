"""
WebSocket stream manager for Binance.

This module provides functionality for managing WebSocket connections and streams.
"""

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any, cast

from binance import ThreadedWebsocketManager

from src.api.common.exceptions import APIError

logger = logging.getLogger(__name__)


class StreamManager:
    """
    Manages WebSocket connections and streams for Binance.

    This class handles the low-level WebSocket connection management,
    including starting/stopping connections, message routing, and error handling.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        on_message: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        """
        Initialize the StreamManager.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Whether to use testnet
            on_message: Callback for all messages
            on_error: Callback for WebSocket errors
            on_close: Callback for WebSocket close
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        # Create the ThreadedWebsocketManager
        self.twm = ThreadedWebsocketManager(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
        )

        # Store active streams for management
        self.active_streams: dict[str, int] = {}  # stream_name -> socket_id
        self._lock = Lock()  # Lock for thread-safe operations on active_streams

        # User-provided callbacks
        self.on_message_callback = on_message
        self.on_error_callback = on_error
        self.on_close_callback = on_close

        # Stream-specific callbacks
        self.stream_callbacks: dict[str, Callable[[dict[str, Any]], None]] = {}

        # Flag to track if the WebSocket manager is running
        self._is_running: bool = False

    def start(self) -> None:
        """Start the WebSocket connection."""
        if not self._is_running:
            try:
                # Start the ThreadedWebsocketManager
                self.twm.start()
                self._is_running = True
                logger.info("Binance WebSocket client started")
            except Exception as e:
                logger.exception("Failed to start Binance WebSocket client")
                raise APIError("Failed to start WebSocket client") from e

    def stop(self) -> None:
        """Stop the WebSocket connection."""
        if self._is_running:
            try:
                # Stop all streams
                self.twm.stop()
                with self._lock:
                    self.active_streams.clear()
                    self.stream_callbacks.clear()
                self._is_running = False
                logger.info("Binance WebSocket client stopped")
            except Exception as e:
                logger.exception("Failed to stop Binance WebSocket client")
                raise APIError("Failed to stop WebSocket client") from e

    @contextmanager
    def acquire_lock(self) -> Iterator[None]:
        """
        Acquire the lock for thread-safe operations.

        This context manager provides safe access to shared resources.

        Yields:
            None
        """
        with self._lock:
            yield

    def add_stream_callback(
        self,
        stream_name: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> None:
        """
        Add a callback for a specific stream.

        Args:
            stream_name: Name of the stream
            callback: Callback function for stream messages
        """
        with self._lock:
            self.stream_callbacks[stream_name] = callback

    def create_message_handler(
        self,
    ) -> Callable[[dict[str, Any]], None]:
        """
        Create a message handler function for a specific stream.

        Args:
            stream_name: Name of the stream

        Returns:
            Message handler function
        """

        def handle_message(msg: dict[str, Any]) -> None:
            # Log the message for debugging
            logger.debug("Received WebSocket message: %s", json.dumps(msg)[:200])

            # Process the message
            self._process_message(msg)

        return handle_message

    def _process_message(self, msg: dict[str, Any]) -> None:
        """
        Process a message received from the WebSocket.

        Args:
            msg: Message received from WebSocket
        """
        # If message is an error, log it and call the error callback
        if "error" in msg:
            error_msg = f"WebSocket error: {msg['error']}"
            logger.error(error_msg)
            if self.on_error_callback:
                self.on_error_callback(APIError(error_msg))
            return

        # Try to get stream name from the message
        stream_name = self._get_stream_name_from_message(msg)

        # Call the specific stream callback if available
        if stream_name and stream_name in self.stream_callbacks:
            try:
                self.stream_callbacks[stream_name](msg)
            except Exception:
                logger.exception("Error in stream callback")
                excp = APIError("Error in stream callback")
                if self.on_error_callback:
                    self.on_error_callback(excp)

        # Always call the general callback if provided
        if self.on_message_callback:
            self.on_message_callback(msg)

    def _get_stream_name_from_message(self, msg: dict[str, Any]) -> str | None:  # noqa: PLR0911
        """
        Extract stream name from a message.

        Args:
            msg: Message received from WebSocket

        Returns:
            Stream name if found, None otherwise
        """
        # Different message types have different structures
        if "stream" in msg:  # Multiplex socket format
            return cast(str, msg["stream"])

        # For single streams, use event type and symbol
        event_type = msg.get("e")
        symbol = msg.get("s", "").lower() if msg.get("s") else None

        # Handle kline event type
        if event_type == "kline" and symbol:
            interval = msg.get("k", {}).get("i")
            if interval:
                return f"{symbol}@kline_{interval}"

        # Handle ticker event type
        elif event_type == "24hrTicker" and symbol:
            return f"{symbol}@ticker"

        # Handle trade event type
        elif event_type == "trade" and symbol:
            return f"{symbol}@trade"

        # Handle depth event type
        elif event_type == "depth" and symbol:
            # Find the depth stream with this symbol in active_streams
            with self._lock:
                for stream_name in self.active_streams:
                    if stream_name.startswith(f"{symbol}@depth"):
                        return stream_name
            # Fallback to the basic depth format
            return f"{symbol}@depth"

        # Return None if we couldn't identify the stream
        return None

    def register_stream(
        self,
        stream_name: str,
        socket_id: int,
        callback: Callable[[dict[str, Any]], None],
    ) -> None:
        """
        Register a stream with the manager.

        Args:
            stream_name: Name of the stream
            socket_id: Socket ID from the ThreadedWebsocketManager
            callback: Callback for stream messages
        """
        with self._lock:
            self.active_streams[stream_name] = socket_id
            self.stream_callbacks[stream_name] = callback

    def unregister_stream(self, stream_name: str) -> None:
        """
        Unregister a stream from the manager.

        Args:
            stream_name: Name of the stream
        """
        with self._lock:
            if stream_name in self.active_streams:
                socket_id = self.active_streams[stream_name]

                # Stop the socket
                self.twm.stop_socket(socket_id)

                # Remove it from managed streams
                del self.active_streams[stream_name]
                if stream_name in self.stream_callbacks:
                    del self.stream_callbacks[stream_name]

                logger.info("Unsubscribed from stream: %s", stream_name)
            else:
                logger.warning(
                    "Attempted to unsubscribe from a non-active stream: %s",
                    stream_name,
                )

    def list_active_streams(self) -> list[str]:
        """
        List active streams.

        Returns:
            List of active stream names
        """
        with self._lock:
            return list(self.active_streams.keys())

    def is_connected(self) -> bool:
        """
        Check if the WebSocket manager is running.

        Returns:
            True if connected, False otherwise
        """
        return self._is_running
