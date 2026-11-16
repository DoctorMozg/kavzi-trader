from datetime import datetime

from kavzi_trader.domain.candlestick import CandlestickSchema


class WarmupKlineSource:
    """Serves each symbol's bars before the replay starts to MarketDataCache."""

    def __init__(self, candles: dict[str, list[CandlestickSchema]]) -> None:
        self._candles = candles

    async def get_klines(
        self,
        symbol: str,
        interval: str,  # noqa: ARG002 - the replay has one bar interval
        start_time: int | datetime | None = None,  # noqa: ARG002
        end_time: int | datetime | None = None,  # noqa: ARG002
        limit: int = 500,
    ) -> list[CandlestickSchema]:
        return self._candles.get(symbol, [])[-limit:]
