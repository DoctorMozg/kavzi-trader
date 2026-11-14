from decimal import Decimal

import pydantic

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.indicator_schemas import TechnicalIndicatorsSchema
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.indicators.config import (
    BollingerParamsSchema,
    EMAPeriodsSchema,
    IndicatorConfigSchema,
)


def test_calculator_empty_candles() -> None:
    calculator = TechnicalIndicatorCalculator()
    result = calculator.calculate([])
    assert result is None


def test_calculator_basic(sample_candles: list[CandlestickSchema]) -> None:
    calculator = TechnicalIndicatorCalculator()
    result = calculator.calculate(sample_candles)

    assert result is not None
    assert isinstance(result, TechnicalIndicatorsSchema)
    lows = [c.low_price for c in sample_candles]
    highs = [c.high_price for c in sample_candles]
    assert result.ema_20 is not None
    assert min(lows) <= result.ema_20 <= max(highs)
    assert result.atr_14 is not None
    assert result.atr_14 > 0


def test_calculator_with_sufficient_data(
    sample_candles: list[CandlestickSchema],
) -> None:
    calculator = TechnicalIndicatorCalculator()
    result = calculator.calculate(sample_candles)

    assert result is not None

    assert result.ema_20 is not None
    assert result.ema_50 is not None
    assert result.ema_200 is None

    assert result.sma_20 is not None
    assert result.rsi_14 is not None
    assert result.macd is not None
    assert result.bollinger is not None
    assert result.atr_14 is not None
    assert result.volume is not None


def test_calculator_timestamp(sample_candles: list[CandlestickSchema]) -> None:
    calculator = TechnicalIndicatorCalculator()
    result = calculator.calculate(sample_candles)

    assert result is not None
    assert result.timestamp == sample_candles[-1].close_time


def test_calculator_trending_up(trending_up_candles: list[CandlestickSchema]) -> None:
    calculator = TechnicalIndicatorCalculator()
    result = calculator.calculate(trending_up_candles)

    assert result is not None

    assert result.rsi_14 is not None
    assert result.rsi_14 > Decimal(50)

    assert result.macd is not None
    assert result.macd.macd_line > Decimal(0)


def test_calculator_trending_down(
    trending_down_candles: list[CandlestickSchema],
) -> None:
    calculator = TechnicalIndicatorCalculator()
    result = calculator.calculate(trending_down_candles)

    assert result is not None

    assert result.rsi_14 is not None
    assert result.rsi_14 < Decimal(50)

    assert result.macd is not None
    assert result.macd.macd_line < Decimal(0)


def test_calculator_custom_params(sample_candles: list[CandlestickSchema]) -> None:
    config = IndicatorConfigSchema(
        ema_periods=EMAPeriodsSchema(short=10, medium=20, long=30),
        rsi_period=7,
        bollinger_params=BollingerParamsSchema(period=10, std_dev=1.5),
        atr_period=7,
    )
    calculator = TechnicalIndicatorCalculator(config=config)
    result = calculator.calculate(sample_candles)

    assert result is not None
    assert result.ema_20 is not None
    assert result.ema_50 is not None
    assert result.bollinger is not None
    default = TechnicalIndicatorCalculator().calculate(sample_candles)
    assert default is not None
    assert result.ema_20 != default.ema_20
    assert result.rsi_14 != default.rsi_14


def test_calculator_frozen_result(sample_candles: list[CandlestickSchema]) -> None:
    calculator = TechnicalIndicatorCalculator()
    result = calculator.calculate(sample_candles)

    assert result is not None

    try:
        result.ema_20 = Decimal(999)  # type: ignore[misc]
        raise AssertionError("Should have raised an error")
    except pydantic.ValidationError:
        pass
