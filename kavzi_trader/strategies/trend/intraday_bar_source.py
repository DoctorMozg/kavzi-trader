import logging

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.strategies.trend.intraday_closes_schema import (
    IntradayClosesSchema,
)

logger = logging.getLogger(__name__)


class IntradayBarSource:
    """Closes of Binance klines of ``hours`` hours, closed bars only."""

    def __init__(self, exchange: ExchangeClient, hours: int) -> None:
        if hours not in (1, 2, 4, 6, 8, 12):
            msg = f"no Binance kline interval of {hours}h"
            raise ValueError(msg)
        self._exchange = exchange
        self._interval = f"{hours}h"

    async def closes(
        self, symbol: str, count: int, now_ms: int
    ) -> IntradayClosesSchema:
        # One extra row, because the still-forming bar is dropped below.
        candles = await self._exchange.get_klines(
            symbol, self._interval, limit=count + 1
        )
        closed = [c for c in candles if c.close_time.timestamp() * 1000 < now_ms]
        closed = closed[-count:]
        logger.debug(
            "Fetched %d closed %s bars for %s", len(closed), self._interval, symbol
        )
        return IntradayClosesSchema(
            open_time_ms=[int(c.open_time.timestamp() * 1000) for c in closed],
            closes=[float(c.close_price) for c in closed],
        )
