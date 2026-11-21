from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.strategies.trend.intraday_bar_source import IntradayBarSource

BAR_S = 6 * 3_600


def _candle(bar: int, close: str) -> CandlestickSchema:
    open_s = bar * BAR_S
    return CandlestickSchema(
        open_time=datetime.fromtimestamp(open_s, UTC),
        open_price=Decimal(1),
        high_price=Decimal(1),
        low_price=Decimal(1),
        close_price=Decimal(close),
        volume=Decimal(1),
        close_time=datetime.fromtimestamp(open_s + BAR_S - 0.001, UTC),
        quote_volume=Decimal(1),
        trades_count=1,
        taker_buy_base_volume=Decimal(1),
        taker_buy_quote_volume=Decimal(1),
    )


async def test_drops_the_forming_bar_and_keeps_open_times() -> None:
    exchange = AsyncMock()
    exchange.get_klines.return_value = [
        _candle(9, "1"),
        _candle(10, "2"),
        _candle(11, "3"),
        _candle(12, "4"),  # still forming
    ]
    now_ms = (12 * BAR_S + 60) * 1000

    bars = await IntradayBarSource(exchange, 6).closes("BTCUSDT", 2, now_ms)

    assert bars.closes == [2.0, 3.0]
    assert bars.open_time_ms == [10 * BAR_S * 1000, 11 * BAR_S * 1000]
    exchange.get_klines.assert_awaited_once_with("BTCUSDT", "6h", limit=3)


def test_rejects_hours_binance_has_no_kline_for() -> None:
    with pytest.raises(ValueError, match="5h"):
        IntradayBarSource(AsyncMock(), 5)
