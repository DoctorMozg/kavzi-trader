from datetime import datetime

from kavzi_trader.domain.candlestick import CandlestickSchema


class ReplayKlineSource:
    """Serves one pre-cut candle window to MarketDataCache.initialize."""

    def __init__(self, candles: list[CandlestickSchema]) -> None:
        self._candles = candles

    async def get_klines(
        self,
        symbol: str,  # noqa: ARG002 - the window is already for one symbol
        interval: str,  # noqa: ARG002
        start_time: int | datetime | None = None,  # noqa: ARG002
        end_time: int | datetime | None = None,  # noqa: ARG002
        limit: int = 500,
    ) -> list[CandlestickSchema]:
        return self._candles[-limit:]
