"""
WebSocket stream manager for Binance.

This module provides functionality for managing WebSocket connections and streams.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, cast

from binance import AsyncClient, BinanceSocketManager, ReconnectingWebsocket

from kavzi_trader.api.common.exceptions import APIError

logger = logging.getLogger(__name__)

# Errors python-binance recovers from itself by reconnecting the socket.
_TRANSIENT_ERROR_TYPES = frozenset(
    {
        "IncompleteReadError",
        "gaierror",
        "ConnectionClosedError",
        "ConnectionClosedOK",
        "BinanceWebsocketClosed",
    },
)


class _StreamEntry(NamedTuple):
    socket: ReconnectingWebsocket
    task: asyncio.Task[None]


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
        on_message: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret

        # Created lazily in start() — requires async AsyncClient.create()
        self._bsm: BinanceSocketManager | None = None
        self._async_client: AsyncClient | None = None

        # stream_name → (socket, recv-loop Task)
        self._streams: dict[str, _StreamEntry] = {}

        # User-provided callbacks
        self.on_message_callback = on_message
        self.on_error_callback = on_error
        self.on_close_callback = on_close

        # Stream-specific callbacks
        self.stream_callbacks: dict[
            str,
            Callable[[dict[str, Any]], Awaitable[None]],
        ] = {}

        self._is_running: bool = False
        # Streams whose feed is dead and will not recover without a restart
        self._dead_streams: set[str] = set()

    @property
    def bsm(self) -> BinanceSocketManager:
        """Return the socket manager; raises if start() has not been called."""
        if self._bsm is None:
            msg = "StreamManager.start() must be called before accessing bsm"
            raise RuntimeError(msg)
        return self._bsm

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the WebSocket connection."""
        if not self._is_running:
            self._async_client = await AsyncClient.create(
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            self._bsm = BinanceSocketManager(self._async_client)
            self._is_running = True
            logger.info("Binance WebSocket client started")

    async def stop(self) -> None:
        """Stop the WebSocket connection and all recv loops."""
        if self._is_running:
            try:
                for stream_name in list(self._streams):
                    await self.unregister_stream(stream_name)

                self._streams.clear()
                self._dead_streams.clear()
                self.stream_callbacks.clear()
                if self._async_client is not None:
                    await self._async_client.close_connection()
                    self._async_client = None
                self._bsm = None
                self._is_running = False
                logger.info("Binance WebSocket client stopped")
            except Exception as ws_error:
                logger.exception(
                    "Failed to stop Binance WebSocket client",
                    extra={"active_streams": list(self._streams.keys())},
                )
                raise APIError("Failed to stop WebSocket client") from ws_error

    # ------------------------------------------------------------------
    # Stream registration
    # ------------------------------------------------------------------

    def add_stream_callback(
        self,
        stream_name: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.stream_callbacks[stream_name] = callback

    def register_stream(
        self,
        stream_name: str,
        socket: ReconnectingWebsocket,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Connect the socket, start a recv loop, and track both."""
        self.stream_callbacks[stream_name] = callback
        task = asyncio.create_task(
            self._recv_loop(stream_name, socket),
        )
        self._streams[stream_name] = _StreamEntry(socket=socket, task=task)

    async def unregister_stream(self, stream_name: str) -> None:
        """Cancel the recv loop (which closes the socket via async with)."""
        entry = self._streams.pop(stream_name, None)
        if entry is None:
            logger.warning(
                "Attempted to unsubscribe from a non-active stream: %s",
                stream_name,
            )
            return

        entry.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry.task
        self.stream_callbacks.pop(stream_name, None)
        logger.info("Unsubscribed from stream: %s", stream_name)

    # ------------------------------------------------------------------
    # Recv loop — pulls messages from the socket and dispatches them
    # ------------------------------------------------------------------

    async def _recv_loop(
        self,
        stream_name: str,
        socket: ReconnectingWebsocket,
    ) -> None:
        """Connect via async with and continuously read messages."""
        try:
            async with socket:
                while True:
                    msg = await socket.recv()
                    if msg is None:
                        continue
                    await self._process_message(msg, stream_name)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Recv loop error for stream %s",
                stream_name,
                extra={"stream_name": stream_name},
            )
            self._dead_streams.add(stream_name)
            if self.on_error_callback:
                self.on_error_callback(
                    APIError(f"Recv loop error for {stream_name}"),
                )

    # ------------------------------------------------------------------
    # Message routing
    # ------------------------------------------------------------------

    async def _process_message(
        self,
        msg: dict[str, Any],
        source_stream: str | None = None,
    ) -> None:
        if msg.get("e") == "error":
            self._handle_error_message(msg, source_stream)
            return

        stream_name = self._get_stream_name_from_message(msg)
        # Combined-stream sockets wrap the event as {"stream": ..., "data": {...}}
        payload = msg["data"] if "stream" in msg and "data" in msg else msg

        if stream_name and stream_name in self.stream_callbacks:
            try:
                await self.stream_callbacks[stream_name](payload)
            except Exception:
                logger.exception(
                    "Error in stream callback",
                    extra={"stream_name": stream_name},
                )
                if self.on_error_callback:
                    self.on_error_callback(
                        APIError("Error in stream callback"),
                    )

        if self.on_message_callback:
            self.on_message_callback(msg)

    def _handle_error_message(
        self,
        msg: dict[str, Any],
        source_stream: str | None,
    ) -> None:
        error_type = str(msg.get("type"))
        error_msg = f"WebSocket error: {error_type}: {msg.get('m')}"
        if error_type in _TRANSIENT_ERROR_TYPES:
            logger.warning(error_msg, extra={"stream_name": source_stream})
            return

        logger.error(error_msg, extra={"stream_name": source_stream})
        self._dead_streams.add(source_stream or "<unknown>")
        if self.on_error_callback:
            self.on_error_callback(APIError(error_msg))

    def _get_stream_name_from_message(  # noqa: PLR0911
        self,
        msg: dict[str, Any],
    ) -> str | None:
        if "stream" in msg:
            return cast("str", msg["stream"])

        event_type = msg.get("e")
        symbol = msg.get("s", "").lower() if msg.get("s") else None

        if event_type == "kline" and symbol:
            interval = msg.get("k", {}).get("i")
            if interval:
                return f"{symbol}@kline_{interval}"

        elif event_type == "24hrTicker" and symbol:
            return f"{symbol}@ticker"

        elif event_type == "trade" and symbol:
            return f"{symbol}@trade"

        elif event_type == "depth" and symbol:
            for sn in self._streams:
                if sn.startswith(f"{symbol}@depth"):
                    return sn
            return f"{symbol}@depth"

        return None

    def list_active_streams(self) -> list[str]:
        return list(self._streams.keys())

    def is_connected(self) -> bool:
        return self._is_running and not self._dead_streams
