from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from kavzi_trader.domain.candlestick import CandlestickSchema

MINUTE_MS = 60_000


def _at(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


class FakeMinuteExchange:
    """Serves 1m klines from a frame of ``open_time_ms`` and ``close``, paged."""

    def __init__(self, minutes: pd.DataFrame) -> None:
        self._minutes = minutes.set_index("open_time_ms")["close"].sort_index()
        self.requests: list[tuple[int, int]] = []

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[CandlestickSchema]:
        assert interval == "1m"
        self.requests.append((start_time, end_time))
        rows = self._minutes.loc[start_time:end_time].iloc[:limit]
        return [
            CandlestickSchema(
                open_time=_at(int(ms)),
                open_price=Decimal(repr(close)),
                high_price=Decimal(repr(close)),
                low_price=Decimal(repr(close)),
                close_price=Decimal(repr(close)),
                volume=Decimal(1),
                close_time=_at(int(ms) + MINUTE_MS - 1),
                quote_volume=Decimal(1),
                trades_count=1,
                taker_buy_base_volume=Decimal(0),
                taker_buy_quote_volume=Decimal(0),
                symbol=symbol,
            )
            for ms, close in rows.items()
        ]
