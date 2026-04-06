import logging
from collections.abc import Awaitable, Callable
from typing import Any

from kavzi_trader.api.binance.schemas.data_dicts import ForceOrderData
from kavzi_trader.api.binance.websocket.handlers.base import BaseStreamHandler

logger = logging.getLogger(__name__)


class ForceOrderStreamHandler(BaseStreamHandler[ForceOrderData]):
    """Handler for Futures liquidation order WebSocket streams."""

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[ForceOrderData], Awaitable[None]],
        **kwargs: Any,  # noqa: ANN401, ARG002
    ) -> str:
        symbol = symbol.lower()
        stream_name = f"{symbol}@forceOrder"

        return await self._start_socket(
            socket_func=self.stream_manager.bsm.symbol_ticker_futures_socket,
            stream_name=stream_name,
            callback=callback,
            symbol=symbol.upper(),
        )
