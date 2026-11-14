from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MACDResultSchema(BaseModel):
    """
    MACD indicator result containing all three components.

    MACD (Moving Average Convergence Divergence) shows momentum by comparing
    fast and slow moving averages.
    """

    macd_line: Decimal
    signal_line: Decimal
    histogram: Decimal

    model_config = ConfigDict(frozen=True)


class BollingerBandsSchema(BaseModel):
    """
    Bollinger Bands result with all band values and derived metrics.

    Bollinger Bands create a price channel that expands/contracts with volatility.
    """

    upper: Decimal
    middle: Decimal
    lower: Decimal
    width: Decimal
    percent_b: Decimal

    model_config = ConfigDict(frozen=True)


class VolumeAnalysisSchema(BaseModel):
    """
    Volume analysis metrics for understanding trade conviction.

    High volume confirms price moves; low volume suggests weakness.
    """

    current_volume: Decimal
    average_volume: Decimal
    volume_ratio: Decimal
    obv: Decimal | None = None

    model_config = ConfigDict(frozen=True)


class TechnicalIndicatorsSchema(BaseModel):
    """
    Complete technical analysis snapshot for a given point in time.

    This schema aggregates all calculated indicators for LLM consumption.
    Each field may be None if insufficient historical data exists.
    """

    ema_20: Decimal | None = None
    ema_50: Decimal | None = None
    ema_200: Decimal | None = None
    sma_20: Decimal | None = None
    rsi_14: Decimal | None = None
    macd: MACDResultSchema | None = None
    bollinger: BollingerBandsSchema | None = None
    atr_14: Decimal | None = None
    volume: VolumeAnalysisSchema | None = None
    timestamp: datetime

    model_config = ConfigDict(frozen=True)
