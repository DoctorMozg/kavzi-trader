from decimal import Decimal

import pandas as pd

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.base import candles_to_dataframe
from kavzi_trader.indicators.momentum import calculate_macd, calculate_rsi
from kavzi_trader.indicators.schemas import MACDResultSchema


def test_calculate_rsi_insufficient_data() -> None:
    series = pd.Series([100, 101, 102])
    result = calculate_rsi(series, period=14)
    assert result is None


def test_calculate_rsi_overbought_condition() -> None:
    prices = [100.0 + i for i in range(50)]
    series = pd.Series(prices)
    result = calculate_rsi(series, period=14)

    assert result is not None
    assert result > Decimal(70)


def test_calculate_rsi_oversold_condition() -> None:
    prices = [150.0 - i for i in range(50)]
    series = pd.Series(prices)
    result = calculate_rsi(series, period=14)

    assert result is not None
    assert result < Decimal(30)


def test_calculate_rsi_neutral() -> None:
    prices = [100, 101, 100, 101, 100, 101, 100, 101] * 5
    series = pd.Series(prices)
    result = calculate_rsi(series, period=14)

    assert result is not None
    assert Decimal(40) < result < Decimal(60)


def test_calculate_rsi_range() -> None:
    prices = list(range(100, 150)) + list(range(150, 100, -1))
    series = pd.Series(prices)
    result = calculate_rsi(series, period=14)

    assert result is not None
    assert Decimal(0) <= result <= Decimal(100)


def test_calculate_macd_insufficient_data() -> None:
    series = pd.Series([100] * 30)
    result = calculate_macd(series)
    assert result is None


def test_calculate_macd_basic() -> None:
    prices = list(range(100, 150))
    series = pd.Series(prices)
    result = calculate_macd(series)

    assert result is not None
    assert isinstance(result, MACDResultSchema)
    assert result.macd_line > Decimal(0)


def test_calculate_macd_bullish_crossover() -> None:
    prices = [100] * 30 + list(range(100, 120))
    series = pd.Series(prices)
    result = calculate_macd(series)

    assert result is not None
    assert result.histogram > Decimal(0)


def test_calculate_macd_bearish_crossover() -> None:
    prices = list(range(150, 100, -1))
    series = pd.Series(prices)
    result = calculate_macd(series)

    assert result is not None
    assert result.macd_line < Decimal(0)


def test_rsi_wilder_smoothing_matches_manual_calculation() -> None:
    """Verify RSI uses Wilder's smoothing (SMA seed, then EMA-style).

    Classic Wilder textbook dataset with 14-period RSI.
    Manual calculation:
      - 19 deltas from 20 prices
      - SMA seed from first 14 gains/losses
      - Wilder smoothing (alpha=1/14) for remaining 5 deltas
      - Expected RSI ~68.07
    A pandas ewm-based RSI would give a different value, catching regressions.
    """
    prices = [
        44,
        44.34,
        44.09,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
        46.00,
        46.03,
        46.41,
        46.22,
        46.21,
    ]
    series = pd.Series(prices)
    result = calculate_rsi(series, period=14)

    assert result is not None
    # Wilder smoothing produces 68.07; pandas ewm gives ~66.25
    assert abs(result - Decimal("68.07")) <= Decimal("0.01")


def test_momentum_with_trending_candles(
    trending_up_candles: list[CandlestickSchema],
) -> None:
    ohlcv = candles_to_dataframe(trending_up_candles)
    close = ohlcv["close"]

    rsi = calculate_rsi(close, period=14)
    macd = calculate_macd(close)

    assert rsi is not None
    assert rsi > Decimal(50)

    assert macd is not None
    assert macd.macd_line > Decimal(0)


def test_momentum_with_downtrend(
    trending_down_candles: list[CandlestickSchema],
) -> None:
    ohlcv = candles_to_dataframe(trending_down_candles)
    close = ohlcv["close"]

    rsi = calculate_rsi(close, period=14)
    macd = calculate_macd(close)

    assert rsi is not None
    assert rsi < Decimal(50)

    assert macd is not None
    assert macd.macd_line < Decimal(0)
