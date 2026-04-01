"""
Binance WebSocket client implementation.

This module provides a WebSocket client for real-time data from Binance.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from kavzi_trader.api.binance.schemas.data_dicts import (
    ForceOrderData,
    KlineData,
    MarkPriceData,
    TickerData,
    TradeData,
)
from kavzi_trader.api.binance.websocket.handlers.depth import DepthStreamHandler
from kavzi_trader.api.binance.websocket.handlers.force_order import (
    ForceOrderStreamHandler,
)
from kavzi_trader.api.binance.websocket.handlers.klines import KlineStreamHandler
from kavzi_trader.api.binance.websocket.handlers.mark_price import (
    MarkPriceStreamHandler,
)
from kavzi_trader.api.binance.websocket.handlers.ticker import TickerStreamHandler
from kavzi_trader.api.binance.websocket.handlers.trades import TradeStreamHandler
from kavzi_trader.api.binance.websocket.handlers.user_data import UserDataStreamHandler
from kavzi_trader.api.binance.websocket.stream_manager import StreamManager
from kavzi_trader.api.common.exceptions import APIError

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
        on_message: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        """
        Initialize the Binance WebSocket client.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            on_message: Callback for all messages
            on_error: Callback for WebSocket errors
            on_close: Callback for WebSocket close
        """
        # Create the stream manager
        self.stream_manager = StreamManager(
            api_key=api_key,
            api_secret=api_secret,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        # Create specialized handlers
        self.kline_handler = KlineStreamHandler(self.stream_manager)
        self.ticker_handler = TickerStreamHandler(self.stream_manager)
        self.trade_handler = TradeStreamHandler(self.stream_manager)
        self.depth_handler = DepthStreamHandler(self.stream_manager)
        self.user_data_handler = UserDataStreamHandler(self.stream_manager)
        self.mark_price_handler = MarkPriceStreamHandler(self.stream_manager)
        self.force_order_handler = ForceOrderStreamHandler(self.stream_manager)

    async def start(self) -> None:
        """Start the WebSocket connection."""
        await self.stream_manager.start()

    async def stop(self) -> None:
        """Stop the WebSocket connection."""
        await self.stream_manager.stop()

    async def subscribe_kline_stream(
        self,
        symbol: str,
        interval: str,
        callback: Callable[[KlineData], Awaitable[None]],
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
        return await self.kline_handler.subscribe(
            symbol=symbol,
            callback=callback,
            interval=interval,
        )

    async def subscribe_ticker_stream(
        self,
        symbol: str,
        callback: Callable[[TickerData], Awaitable[None]],
    ) -> str:
        """
        Subscribe to 24hr ticker updates stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for ticker data

        Returns:
            Stream name
        """
        return await self.ticker_handler.subscribe(
            symbol=symbol,
            callback=callback,
        )

    async def subscribe_trades_stream(
        self,
        symbol: str,
        callback: Callable[[TradeData], Awaitable[None]],
    ) -> str:
        """
        Subscribe to trade updates stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for trade data

        Returns:
            Stream name
        """
        return await self.trade_handler.subscribe(
            symbol=symbol,
            callback=callback,
        )

    async def subscribe_depth_stream(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
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
        return await self.depth_handler.subscribe(
            symbol=symbol,
            callback=callback,
            depth=depth,
        )

    async def subscribe_multiplex_streams(
        self,
        streams: list[str],
        callback: Callable[[dict[str, Any]], Awaitable[None]],
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
        for stream in streams:
            self.stream_manager.add_stream_callback(
                stream_name=stream,
                callback=callback,
            )

        # Ensure the WebSocket manager is running
        await self.stream_manager.start()

        try:
            # Get a ReconnectingWebsocket for the multiplex stream
            socket = self.stream_manager.bsm.multiplex_socket(
                streams=streams,
            )

            # Register → connects, starts recv loop, tracks callback
            self.stream_manager.register_stream(
                stream_name=stream_id,
                socket=socket,
                callback=callback,
            )

            logger.info("Subscribed to multiplex streams: %s", stream_id)
        except Exception as err:
            logger.exception("Failed to subscribe to multiplex streams")
            raise APIError("Failed to subscribe to multiplex streams") from err
        else:
            return stream_id

    async def subscribe_user_data_stream(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> str:
        """
        Subscribe to user data stream for account and order updates.

        Args:
            callback: Callback for user data events

        Returns:
            Stream name (user-data-stream-id)
        """
        return await self.user_data_handler.subscribe(
            callback=callback,
        )

    async def unsubscribe_stream(self, stream_name: str) -> None:
        """
        Unsubscribe from a stream.

        Args:
            stream_name: Name of the stream to unsubscribe from
        """
        await self.stream_manager.unregister_stream(stream_name)

    async def unsubscribe_all_streams(self) -> None:
        """Unsubscribe from all active streams and stop the WebSocket manager."""
        await self.stream_manager.stop()

    def list_active_streams(self) -> list[str]:
        """
        List active streams.

        Returns:
            List of active stream names
        """
        return self.stream_manager.list_active_streams()

    def is_connected(self) -> bool:
        """
        Check if the WebSocket manager is running.

        Returns:
            True if connected, False otherwise
        """
        return self.stream_manager.is_connected()

    async def subscribe_mark_price_stream(
        self,
        symbol: str,
        callback: Callable[[MarkPriceData], Awaitable[None]],
        update_speed: str = "1s",
    ) -> str:
        """
        Subscribe to Futures mark price stream (includes funding rate).

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for mark price data
            update_speed: Update speed ("1s" or "3s")

        Returns:
            Stream name
        """
        return await self.mark_price_handler.subscribe(
            symbol=symbol,
            callback=callback,
            update_speed=update_speed,
        )

    async def subscribe_force_order_stream(
        self,
        symbol: str,
        callback: Callable[[ForceOrderData], Awaitable[None]],
    ) -> str:
        """
        Subscribe to Futures liquidation order stream.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Callback for liquidation data

        Returns:
            Stream name
        """
        return await self.force_order_handler.subscribe(
            symbol=symbol,
            callback=callback,
        )
