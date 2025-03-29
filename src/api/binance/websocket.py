"""
Binance WebSocket client implementation.

This module provides a WebSocket client for real-time data from Binance.
"""

import json
import logging
from collections.abc import Callable
from threading import Lock
from typing import Any, cast

from binance import ThreadedWebsocketManager
from binance.exceptions import BinanceAPIException

from src.api.binance.constants import KLINE_INTERVALS
from src.api.binance.schemas.callback import KlineData, TickerData, TradeData
from src.api.common.exceptions import APIError

logger = logging.getLogger(__name__)


class BinanceWebsocketClient:
    """
    Binance WebSocket client for real-time market data.

    This class provides methods to stream market data from Binance using WebSockets.
    It wraps the python-binance library's ThreadedWebsocketManager for easier
    integration.
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
        Initialize the Binance WebSocket client.

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
        self._is_running = False

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

    def _create_message_handler(
        self,
        _stream_name: str,  # We're not using this parameter directly
    ) -> Callable[[dict[str, Any]], None]:
        """
        Create a message handler function for a specific stream.

        Args:
            _stream_name: Name of the stream (unused but kept for API compatibility)

        Returns:
            Message handler function
        """

        def handle_message(msg: dict[str, Any]) -> None:
            # Log the message for debugging
            logger.debug("Received WebSocket message: %s", json.dumps(msg)[:200])

            # Process the message
            self._process_message(msg)

        return handle_message

    def subscribe_kline_stream(
        self,
        symbol: str,
        interval: str,
        callback: Callable[[KlineData], None],
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

        # Store the callback
        with self._lock:
            self.stream_callbacks[stream_name] = callback  # type: ignore

        # Ensure the WebSocket manager is running
        self.start()

        try:
            # Start the kline socket
            socket_id = self.twm.start_kline_socket(
                callback=self._create_message_handler(stream_name),
                symbol=symbol.upper(),
                interval=interval,
            )

            # Store the socket ID for management
            with self._lock:
                self.active_streams[stream_name] = socket_id

            logger.info("Subscribed to kline stream: %s", stream_name)
        except BinanceAPIException as err:
            logger.exception("Failed to subscribe to kline stream")
            raise APIError(f"Failed to subscribe to kline stream: {err!s}") from err
        else:
            return stream_name

    def subscribe_ticker_stream(
        self,
        symbol: str,
        callback: Callable[[TickerData], None],
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

        # Store the callback
        with self._lock:
            self.stream_callbacks[stream_name] = callback  # type: ignore

        # Ensure the WebSocket manager is running
        self.start()

        try:
            # Start the symbol ticker socket
            socket_id = self.twm.start_symbol_ticker_socket(
                callback=self._create_message_handler(stream_name),
                symbol=symbol.upper(),
            )

            # Store the socket ID for management
            with self._lock:
                self.active_streams[stream_name] = socket_id

            logger.info("Subscribed to ticker stream: %s", stream_name)
        except BinanceAPIException as err:
            logger.exception("Failed to subscribe to ticker stream")
            raise APIError("Failed to subscribe to ticker stream") from err
        else:
            return stream_name

    def subscribe_trades_stream(
        self,
        symbol: str,
        callback: Callable[[TradeData], None],
    ) -> str:
        """
        Subscribe to trade updates stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for trade data

        Returns:
            Stream name
        """
        symbol = symbol.lower()
        stream_name = f"{symbol}@trade"

        # Store the callback
        with self._lock:
            self.stream_callbacks[stream_name] = callback  # type: ignore

        # Ensure the WebSocket manager is running
        self.start()

        try:
            # Start the trade socket
            socket_id = self.twm.start_trade_socket(
                callback=self._create_message_handler(stream_name),
                symbol=symbol.upper(),
            )

            # Store the socket ID for management
            with self._lock:
                self.active_streams[stream_name] = socket_id

            logger.info("Subscribed to trades stream: %s", stream_name)
        except BinanceAPIException as err:
            logger.exception("Failed to subscribe to trades stream")
            raise APIError("Failed to subscribe to trades stream") from err
        else:
            return stream_name

    def subscribe_depth_stream(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], None],
        depth: int = 20,
    ) -> str:
        """
        Subscribe to order book depth stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for depth data
            depth: Depth of the order book (5, 10, or 20)

        Returns:
            Stream name
        """
        if depth not in (5, 10, 20):
            raise ValueError("Depth must be 5, 10, or 20")

        symbol = symbol.lower()
        stream_name = f"{symbol}@depth{depth}"

        # Store the callback
        with self._lock:
            self.stream_callbacks[stream_name] = callback

        # Ensure the WebSocket manager is running
        self.start()

        try:
            # Start the depth socket
            socket_id = self.twm.start_depth_socket(
                callback=self._create_message_handler(stream_name),
                symbol=symbol.upper(),
                depth=depth,
            )

            # Store the socket ID for management
            with self._lock:
                self.active_streams[stream_name] = socket_id

            logger.info("Subscribed to depth stream: %s", stream_name)
        except BinanceAPIException as err:
            logger.exception("Failed to subscribe to depth stream")
            raise APIError("Failed to subscribe to depth stream") from err
        else:
            return stream_name

    def subscribe_multiplex_streams(
        self,
        streams: list[str],
        callback: Callable[[dict[str, Any]], None],
    ) -> str:
        """
        Subscribe to multiple streams at once.

        Args:
            streams: List of stream names
            callback: Callback for stream data

        Returns:
            Multiplex stream ID
        """
        if not streams:
            raise ValueError("At least one stream must be provided")

        # Store streams as lowercase
        streams = [s.lower() for s in streams]
        stream_id = "/".join(streams)

        # Store the callback for each individual stream
        with self._lock:
            for stream in streams:
                self.stream_callbacks[stream] = callback

        # Ensure the WebSocket manager is running
        self.start()

        try:
            # Start the multiplex socket
            socket_id = self.twm.start_multiplex_socket(
                callback=self._create_message_handler(stream_id),
                streams=streams,
            )

            # Store the socket ID for management
            with self._lock:
                self.active_streams[stream_id] = socket_id

            logger.info("Subscribed to multiplex streams: %s", stream_id)
        except BinanceAPIException as err:
            logger.exception("Failed to subscribe to multiplex streams")
            raise APIError("Failed to subscribe to multiplex streams") from err
        else:
            return stream_id

    def subscribe_user_data_stream(
        self,
        callback: Callable[[dict[str, Any]], None],
    ) -> str:
        """
        Subscribe to user data stream for account and order updates.

        Args:
            callback: Callback for user data events

        Returns:
            Stream name (user-data-stream-id)
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret are required for user data stream")

        stream_name = "user-data-stream"

        # Store the callback
        with self._lock:
            self.stream_callbacks[stream_name] = callback

        # Ensure the WebSocket manager is running
        self.start()

        try:
            # Start the user data socket
            socket_id = self.twm.start_user_socket(
                callback=self._create_message_handler(stream_name),
            )

            # Store the socket ID for management
            with self._lock:
                self.active_streams[stream_name] = socket_id

            logger.info("Subscribed to user data stream")
        except BinanceAPIException as err:
            logger.exception("Failed to subscribe to user data stream")
            raise APIError("Failed to subscribe to user data stream") from err
        else:
            return stream_name

    def unsubscribe_stream(self, stream_name: str) -> None:
        """
        Unsubscribe from a stream.

        Args:
            stream_name: Name of the stream to unsubscribe from
        """
        stream_name = stream_name.lower()

        try:
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
        except Exception as err:
            logger.exception("Error unsubscribing from stream")
            raise APIError(f"Error unsubscribing from stream: {err!s}") from err

    def unsubscribe_all_streams(self) -> None:
        """Unsubscribe from all active streams and stop the WebSocket manager."""
        try:
            # Stop the WebSocket manager (disconnects all sockets)
            self.stop()

            # Clear all active streams and callbacks
            with self._lock:
                self.active_streams.clear()
                self.stream_callbacks.clear()

            logger.info("Unsubscribed from all streams")
        except Exception as err:
            logger.exception("Error unsubscribing from all streams")
            msg = "Error unsubscribing from all streams"
            raise APIError(f"{msg}: {err!s}") from err

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
