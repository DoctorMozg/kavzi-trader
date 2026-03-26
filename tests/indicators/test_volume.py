from decimal import Decimal

import pandas as pd

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.base import candles_to_dataframe
from kavzi_trader.indicators.schemas import VolumeAnalysisSchema
from kavzi_trader.indicators.volume import (
    calculate_obv,
    calculate_volume_analysis,
)


def test_calculate_obv_insufficient_data() -> None:
    close = pd.Series([100.0])
    volume = pd.Series([1000.0])
    result = calculate_obv(close, volume)
    assert result is None


def test_calculate_obv_rising_prices() -> None:
    close = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
    volume = pd.Series([1000.0, 1000.0, 1000.0, 1000.0, 1000.0])
    result = calculate_obv(close, volume)

    assert result is not None
    assert result > Decimal(0)


def test_calculate_obv_falling_prices() -> None:
    close = pd.Series([104.0, 103.0, 102.0, 101.0, 100.0])
    volume = pd.Series([1000.0, 1000.0, 1000.0, 1000.0, 1000.0])
    result = calculate_obv(close, volume)

    assert result is not None
    assert result < Decimal(0)


def test_calculate_obv_mixed() -> None:
    close = pd.Series([100.0, 101.0, 100.0, 101.0, 100.0])
    volume = pd.Series([1000.0, 1000.0, 1000.0, 1000.0, 1000.0])
    result = calculate_obv(close, volume)

    assert result is not None
    assert result == Decimal(0)


def test_calculate_volume_analysis_insufficient_data() -> None:
    close = pd.Series([100.0] * 10)
    volume = pd.Series([1000.0] * 10)
    result = calculate_volume_analysis(close, volume, period=20)
    assert result is None


def test_calculate_volume_analysis_basic() -> None:
    close = pd.Series([100.0 + i for i in range(30)])
    volume = pd.Series([1000.0] * 30)
    result = calculate_volume_analysis(close, volume, period=20)

    assert result is not None
    assert isinstance(result, VolumeAnalysisSchema)
    assert result.current_volume == Decimal("1000.0")
    assert result.average_volume == Decimal("1000.0")
    assert result.volume_ratio == Decimal("1.0")


def test_calculate_volume_analysis_high_volume() -> None:
    volumes = [1000.0] * 29 + [5000.0]
    close = pd.Series([100.0 + i for i in range(30)])
    volume = pd.Series(volumes)
    result = calculate_volume_analysis(close, volume, period=20)

    assert result is not None
    assert result.volume_ratio > Decimal("1.5")


def test_calculate_volume_analysis_low_volume() -> None:
    volumes = [1000.0] * 29 + [100.0]
    close = pd.Series([100.0 + i for i in range(30)])
    volume = pd.Series(volumes)
    result = calculate_volume_analysis(close, volume, period=20)

    assert result is not None
    assert result.volume_ratio < Decimal("0.5")


def test_volume_with_candles(sample_candles: list[CandlestickSchema]) -> None:
    ohlcv = candles_to_dataframe(sample_candles)

    result = calculate_volume_analysis(ohlcv["close"], ohlcv["volume"], period=20)

    assert result is not None
    assert result.obv is not None
    assert result.current_volume > Decimal(0)
    assert result.average_volume > Decimal(0)
