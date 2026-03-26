from decimal import Decimal

import pandas as pd

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.base import candles_to_dataframe
from kavzi_trader.indicators.schemas import BollingerBandsSchema
from kavzi_trader.indicators.volatility import (
    calculate_atr,
    calculate_bollinger_bands,
)


def test_calculate_atr_insufficient_data() -> None:
    high = pd.Series([101, 102, 103])
    low = pd.Series([99, 100, 101])
    close = pd.Series([100, 101, 102])
    result = calculate_atr(high, low, close, period=14)
    assert result is None


def test_calculate_atr_basic() -> None:
    high = pd.Series([i + 2 for i in range(100, 130)])
    low = pd.Series([i - 2 for i in range(100, 130)])
    close = pd.Series(list(range(100, 130)))

    result = calculate_atr(high, low, close, period=14)

    assert result is not None
    assert result > Decimal(0)


def test_calculate_atr_volatile_vs_calm() -> None:
    calm_high = pd.Series([101.0] * 30)
    calm_low = pd.Series([99.0] * 30)
    calm_close = pd.Series([100.0] * 30)

    volatile_high = pd.Series([i + 10 for i in range(100, 130)])
    volatile_low = pd.Series([i - 10 for i in range(100, 130)])
    volatile_close = pd.Series(list(range(100, 130)))

    calm_atr = calculate_atr(calm_high, calm_low, calm_close, period=14)
    volatile_atr = calculate_atr(volatile_high, volatile_low, volatile_close, period=14)

    assert calm_atr is not None
    assert volatile_atr is not None
    assert volatile_atr > calm_atr


def test_calculate_bollinger_insufficient_data() -> None:
    series = pd.Series([100] * 10)
    result = calculate_bollinger_bands(series, period=20)
    assert result is None


def test_calculate_bollinger_basic() -> None:
    series = pd.Series([100.0] * 30)
    result = calculate_bollinger_bands(series, period=20)

    assert result is not None
    assert isinstance(result, BollingerBandsSchema)
    assert result.middle == Decimal("100.0")


def test_calculate_bollinger_band_ordering() -> None:
    prices = [100 + (i % 5) for i in range(30)]
    series = pd.Series(prices)
    result = calculate_bollinger_bands(series, period=20)

    assert result is not None
    assert result.lower < result.middle < result.upper


def test_calculate_bollinger_percent_b() -> None:
    prices = [100.0] * 30
    series = pd.Series(prices)
    result = calculate_bollinger_bands(series, period=20)

    assert result is not None
    assert Decimal("0.4") < result.percent_b < Decimal("0.6")


def test_calculate_bollinger_width_expands_with_volatility() -> None:
    calm_prices = [100.0] * 30
    volatile_prices = [100 + (i % 10) * (1 if i % 2 == 0 else -1) for i in range(30)]

    calm_bb = calculate_bollinger_bands(pd.Series(calm_prices), period=20)
    volatile_bb = calculate_bollinger_bands(pd.Series(volatile_prices), period=20)

    assert calm_bb is not None
    assert volatile_bb is not None
    assert volatile_bb.width > calm_bb.width


def test_volatility_with_candles(sample_candles: list[CandlestickSchema]) -> None:
    ohlcv = candles_to_dataframe(sample_candles)

    atr = calculate_atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], period=14)
    bb = calculate_bollinger_bands(ohlcv["close"], period=20)

    assert atr is not None
    assert atr > Decimal(0)

    assert bb is not None
    assert bb.lower < bb.middle < bb.upper
