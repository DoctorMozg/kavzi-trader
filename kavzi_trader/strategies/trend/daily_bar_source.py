import logging

import numpy as np

from kavzi_trader.api.exchange_client import ExchangeClient

logger = logging.getLogger(__name__)


class DailyBarSource:
    """Daily closes from Binance 1d klines, closed days only."""

    def __init__(self, exchange: ExchangeClient) -> None:
        self._exchange = exchange

    async def closes(self, symbol: str, days: int, now_ms: int) -> np.ndarray:
        # One extra row, because the still-forming day is dropped below.
        candles = await self._exchange.get_klines(symbol, "1d", limit=days + 1)
        closed = [c for c in candles if c.close_time.timestamp() * 1000 < now_ms]
        logger.debug("Fetched %d closed daily bars for %s", len(closed), symbol)
        return np.array([float(c.close_price) for c in closed[-days:]])
