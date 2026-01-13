import logging
from collections.abc import Awaitable, Callable
from typing import Any

from kavzi_trader.api.binance.schemas.data_dicts import MarkPriceData
from kavzi_trader.api.binance.websocket.handlers.base import BaseStreamHandler
from kavzi_trader.api.binance.websocket.stream_manager import StreamManager

logger = logging.getLogger(__name__)


class MarkPriceStreamHandler(BaseStreamHandler[MarkPriceData]):
    """Handler for Futures mark price WebSocket streams (includes funding rate)."""

    def __init__(self, stream_manager: StreamManager) -> None:
        super().__init__(stream_manager)

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[MarkPriceData], Awaitable[None]],
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        symbol = symbol.lower()
        update_speed = kwargs.get("update_speed", "1s")
        stream_name = f"{symbol}@markPrice@{update_speed}"

        return await self._start_socket(
            socket_func=self.stream_manager.bsm.symbol_mark_price_socket,
            stream_name=stream_name,
            callback=callback,
            symbol=symbol.upper(),
        )
