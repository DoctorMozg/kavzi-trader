from decimal import Decimal

import pandas as pd

from kavzi_trader.indicators.schemas import BollingerBandsSchema


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> Decimal | None:
    """
    Calculate Average True Range (ATR).

    ATR measures how much price typically moves in a period, showing volatility
    regardless of price direction. Higher ATR means more volatile/risky market.

    True Range is the greatest of:
        - Current High minus Current Low
        - Absolute value of Current High minus Previous Close
        - Absolute value of Current Low minus Previous Close

    Interpretation:
        - High ATR: Volatile market, larger price swings expected
        - Low ATR: Calm market, smaller price movements
        - Rising ATR: Increasing volatility (often during trends or breakouts)
        - Falling ATR: Decreasing volatility (often during consolidation)

    Common trading uses:
        - Setting stop-loss distances (e.g., 2x ATR below entry)
        - Position sizing (smaller positions in high ATR environments)
        - Identifying volatility regime changes
        - Trailing stop adjustments

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ATR period (default 14)

    Returns:
        ATR value in price units, or None if insufficient data
    """
    if len(close) < period + 1:
        return None

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    return Decimal(str(round(atr.iloc[-1], 8)))


def calculate_bollinger_bands(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> BollingerBandsSchema | None:
    """
    Calculate Bollinger Bands.

    Bollinger Bands create a price "channel" around a moving average. The bands
    expand when volatility increases and contract when it decreases.

    Components:
        - Middle Band: 20-period SMA (the average)
        - Upper Band: Middle + (2 x standard deviation)
        - Lower Band: Middle - (2 x standard deviation)
        - Band Width: (Upper - Lower) / Middle (measures volatility)
        - %B: Where price is within the bands (0 = lower, 1 = upper)

    Interpretation:
        - Price near upper band: Potentially overbought
        - Price near lower band: Potentially oversold
        - Narrow bands (squeeze): Low volatility, big move may be coming
        - Wide bands: High volatility, possibly overextended

    Common trading uses:
        - Mean reversion trading (buy at lower band, sell at upper)
        - Breakout identification (price breaking through bands)
        - Volatility assessment via band width
        - Trend following (walking the bands in strong trends)

    Args:
        series: Price series (typically close prices)
        period: Moving average period (default 20)
        std_dev: Number of standard deviations (default 2.0)

    Returns:
        BollingerBandsSchema with upper, middle, lower bands, width, and percent_b
    """
    if len(series) < period:
        return None

    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()

    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)

    current_middle = middle.iloc[-1]
    current_upper = upper.iloc[-1]
    current_lower = lower.iloc[-1]
    current_close = series.iloc[-1]

    if pd.isna(current_middle) or pd.isna(current_upper) or pd.isna(current_lower):
        return None

    band_width = (
        (current_upper - current_lower) / current_middle if current_middle else 0
    )
    band_range = current_upper - current_lower
    percent_b = (current_close - current_lower) / band_range if band_range > 0 else 0.5

    return BollingerBandsSchema(
        upper=Decimal(str(round(current_upper, 8))),
        middle=Decimal(str(round(current_middle, 8))),
        lower=Decimal(str(round(current_lower, 8))),
        width=Decimal(str(round(band_width, 8))),
        percent_b=Decimal(str(round(percent_b, 4))),
    )
