"""
User data stream handler for Binance WebSocket.

This module provides a handler for user data WebSocket streams.
"""

import logging
from collections.abc import Callable
from typing import Any, Awaitable

from src.api.binance.websocket.handlers.base import BaseStreamHandler
from src.api.binance.websocket.stream_manager import StreamManager

logger = logging.getLogger(__name__)


class UserDataStreamHandler(BaseStreamHandler[dict[str, Any]]):
    """Handler for user data WebSocket streams."""

    def __init__(self, stream_manager: StreamManager) -> None:
        """Initialize the UserDataStreamHandler."""
        super().__init__(stream_manager)

    async def subscribe(
        self,
        symbol: str = "",  # Not used for user data streams # noqa: ARG002
        callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        **kwargs: Any,  # noqa: ARG002,ANN401
    ) -> str:
        """
        Subscribe to user data stream for account and order updates.

        Args:
            symbol: Not used for user data streams
            callback: Callback for user data events
            **kwargs: Additional parameters (not used for user data streams)

        Returns:
            Stream name
        """
        if not self.stream_manager.api_key or not self.stream_manager.api_secret:
            raise ValueError("API key and secret are required for user data stream")

        if callback is None:
            raise ValueError("Callback is required for user data stream")

        stream_name = "user-data-stream"

        return await self._start_socket(
            socket_func=self.stream_manager.bsm.user_socket,
            stream_name=stream_name,
            callback=callback,
        )
