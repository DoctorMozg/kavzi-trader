from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.strategies.trend.daily_bar_source import DailyBarSource

DAY_S = 86_400


def _candle(day: int, close: str) -> CandlestickSchema:
    open_s = day * DAY_S
    return CandlestickSchema(
        open_time=datetime.fromtimestamp(open_s, UTC),
        open_price=Decimal(1),
        high_price=Decimal(1),
        low_price=Decimal(1),
        close_price=Decimal(close),
        volume=Decimal(1),
        close_time=datetime.fromtimestamp(open_s + DAY_S - 0.001, UTC),
        quote_volume=Decimal(1),
        trades_count=1,
        taker_buy_base_volume=Decimal(1),
        taker_buy_quote_volume=Decimal(1),
    )


async def test_drops_the_forming_day_and_keeps_the_newest_closed_bars() -> None:
    exchange = AsyncMock()
    exchange.get_klines.return_value = [
        _candle(9, "1"),
        _candle(10, "2"),
        _candle(11, "3"),
        _candle(12, "4"),  # still forming
    ]
    now_ms = (12 * DAY_S + 60) * 1000

    closes = await DailyBarSource(exchange).closes("BTCUSDT", 2, now_ms)

    assert closes.tolist() == [2.0, 3.0]
    exchange.get_klines.assert_awaited_once_with("BTCUSDT", "1d", limit=3)
