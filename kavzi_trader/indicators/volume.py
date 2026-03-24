from decimal import Decimal

import pandas as pd

from kavzi_trader.indicators.schemas import VolumeAnalysisSchema


def calculate_obv(close: pd.Series, volume: pd.Series) -> Decimal | None:
    """
    Calculate On-Balance Volume (OBV).

    OBV tracks buying/selling pressure using volume. It adds volume on up days
    and subtracts volume on down days, creating a cumulative total.

    Interpretation:
        - Rising OBV: Buyers are in control, accumulation happening
        - Falling OBV: Sellers are in control, distribution happening
        - OBV divergence from price: Potential reversal signal
            - Price up but OBV down = bearish divergence (weakness)
            - Price down but OBV up = bullish divergence (strength)

    Common trading uses:
        - Confirming price trends (OBV should move with price)
        - Spotting divergences before price reversals
        - Identifying accumulation/distribution phases

    Args:
        close: Close price series
        volume: Volume series

    Returns:
        Current OBV value, or None if insufficient data
    """
    min_periods = 2
    if len(close) < min_periods:
        return None

    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (direction * volume).cumsum()

    return Decimal(str(round(obv.iloc[-1], 2)))


def calculate_volume_ratios(
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> VolumeAnalysisSchema | None:
    """
    Calculate volume analysis metrics.

    Volume analysis helps understand the conviction behind price movements.
    High volume confirms moves; low volume suggests weakness.

    Metrics:
        - Current Volume: Latest bar's volume
        - Average Volume: 20-period average
        - Volume Ratio: Current / Average (>1 = above average, <1 = below)

    Interpretation:
        - Ratio > 1.5: High volume, strong conviction in current move
        - Ratio 0.8-1.2: Normal volume
        - Ratio < 0.5: Low volume, weak conviction, possible fake move

    Common trading uses:
        - Confirming breakouts (need high volume)
        - Identifying exhaustion (extreme volume at tops/bottoms)
        - Filtering signals (reject low-volume moves)

    Args:
        volume: Volume series
        period: Period for average volume calculation (default 20)

    Returns:
        VolumeAnalysisSchema with current, average, and ratio
    """
    if len(volume) < period:
        return None

    current = volume.iloc[-1]
    average = volume.rolling(window=period).mean().iloc[-1]
    ratio = current / average if average > 0 else 1.0

    return VolumeAnalysisSchema(
        current_volume=Decimal(str(round(current, 2))),
        average_volume=Decimal(str(round(average, 2))),
        volume_ratio=Decimal(str(round(ratio, 4))),
        obv=calculate_obv(close, volume),
    )


def calculate_volume_analysis(
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> VolumeAnalysisSchema | None:
    """
    Calculate complete volume analysis including OBV.

    Args:
        close: Close price series
        volume: Volume series
        period: Period for average volume calculation

    Returns:
        VolumeAnalysisSchema with all metrics
    """
    if len(volume) < period:
        return None

    current = volume.iloc[-1]
    average = volume.rolling(window=period).mean().iloc[-1]
    ratio = current / average if average > 0 else 1.0
    obv = calculate_obv(close, volume)

    return VolumeAnalysisSchema(
        current_volume=Decimal(str(round(current, 2))),
        average_volume=Decimal(str(round(average, 2))),
        volume_ratio=Decimal(str(round(ratio, 4))),
        obv=obv,
    )
