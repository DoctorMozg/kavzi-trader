from decimal import Decimal

import pandas as pd

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.base import candles_to_dataframe
from kavzi_trader.indicators.trend import calculate_ema, calculate_sma


def test_calculate_ema_insufficient_data() -> None:
    series = pd.Series([100, 101, 102])
    result = calculate_ema(series, period=20)
    assert result is None


def test_calculate_ema_basic() -> None:
    series = pd.Series(range(100, 130))
    result = calculate_ema(series, period=20)

    assert result is not None
    assert isinstance(result, Decimal)
    assert result > Decimal(100)


def test_calculate_ema_responds_to_recent_prices() -> None:
    base_prices = [100.0] * 30
    rising_prices = base_prices.copy()
    rising_prices[-5:] = [110, 115, 120, 125, 130]

    flat_ema = calculate_ema(pd.Series(base_prices), period=20)
    rising_ema = calculate_ema(pd.Series(rising_prices), period=20)

    assert flat_ema is not None
    assert rising_ema is not None
    assert rising_ema > flat_ema


def test_calculate_sma_insufficient_data() -> None:
    series = pd.Series([100, 101, 102])
    result = calculate_sma(series, period=20)
    assert result is None


def test_calculate_sma_basic() -> None:
    prices = [100.0] * 20
    series = pd.Series(prices)
    result = calculate_sma(series, period=20)

    assert result is not None
    assert result == Decimal("100.0")


def test_calculate_sma_simple_average() -> None:
    prices = list(range(1, 21))
    series = pd.Series(prices)
    result = calculate_sma(series, period=20)

    expected = sum(prices) / len(prices)
    assert result is not None
    assert result == Decimal(str(expected))


def test_ema_vs_sma_responsiveness() -> None:
    base_prices = [100.0] * 25
    base_prices[-5:] = [110, 120, 130, 140, 150]
    series = pd.Series(base_prices)

    ema = calculate_ema(series, period=20)
    sma = calculate_sma(series, period=20)

    assert ema is not None
    assert sma is not None
    assert ema > sma


def test_trend_indicators_with_candles(
    trending_up_candles: list[CandlestickSchema],
) -> None:
    ohlcv = candles_to_dataframe(trending_up_candles)
    close = ohlcv["close"]

    ema_20 = calculate_ema(close, 20)
    ema_50 = calculate_ema(close, 50)

    assert ema_20 is not None
    assert ema_50 is not None

    last_close = Decimal(str(close.iloc[-1]))
    assert ema_20 < last_close
    assert ema_50 < ema_20
