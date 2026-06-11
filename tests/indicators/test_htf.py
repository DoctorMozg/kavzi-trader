from datetime import UTC, datetime, timedelta
from decimal import Decimal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.htf import aggregate_1h_closes, compute_htf_trend

_START = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(index: int, close: Decimal) -> CandlestickSchema:
    open_time = _START + timedelta(minutes=15 * index)
    return CandlestickSchema(
        open_time=open_time,
        open_price=close,
        high_price=close,
        low_price=close,
        close_price=close,
        volume=Decimal(1),
        close_time=open_time + timedelta(minutes=15),
        quote_volume=Decimal(1),
        trades_count=1,
        taker_buy_base_volume=Decimal("0.5"),
        taker_buy_quote_volume=Decimal("0.5"),
        interval="15m",
        symbol="BTCUSDT",
    )


def _series(closes: list[Decimal]) -> list[CandlestickSchema]:
    return [_candle(i, c) for i, c in enumerate(closes)]


def test_aggregate_takes_last_close_per_hour() -> None:
    # 8 15m candles = 2 hours; each hour's close is its 4th candle.
    closes = [Decimal(n) for n in (10, 11, 12, 13, 20, 21, 22, 23)]
    result = aggregate_1h_closes(_series(closes))
    assert result == [Decimal(13), Decimal(23)]


def test_partial_final_hour_is_kept() -> None:
    # 6 candles = 1 full hour + a 2-candle partial hour.
    closes = [Decimal(n) for n in (10, 11, 12, 13, 20, 21)]
    result = aggregate_1h_closes(_series(closes))
    assert result == [Decimal(13), Decimal(21)]


def test_insufficient_history_is_neutral() -> None:
    # Fewer than 50 1h bars (40 candles = 10 hours) → NEUTRAL, no guess.
    trend = compute_htf_trend(_series([Decimal(100)] * 40))
    assert trend.direction == "NEUTRAL"
    assert trend.bars_1h == 10


def test_rising_series_is_long() -> None:
    # 240 candles = 60 1h bars, monotonically rising → EMA20 > EMA50, RSI > 50.
    closes = [Decimal(100) + Decimal(i) for i in range(240)]
    trend = compute_htf_trend(_series(closes))
    assert trend.direction == "LONG"
    assert trend.ema_20 is not None
    assert trend.ema_50 is not None
    assert trend.ema_20 > trend.ema_50


def test_falling_series_is_short() -> None:
    closes = [Decimal(1000) - Decimal(i) for i in range(240)]
    trend = compute_htf_trend(_series(closes))
    assert trend.direction == "SHORT"
    assert trend.ema_20 is not None
    assert trend.ema_50 is not None
    assert trend.ema_20 < trend.ema_50


def test_flat_series_is_neutral() -> None:
    # Enough history but no directional stack → NEUTRAL.
    trend = compute_htf_trend(_series([Decimal(100)] * 240))
    assert trend.direction == "NEUTRAL"
    assert trend.bars_1h == 60
