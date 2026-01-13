from decimal import Decimal

import pandas as pd


def calculate_ema(series: pd.Series, period: int) -> Decimal | None:
    """
    Calculate Exponential Moving Average (EMA) for the given period.

    EMA is a smoothed average of recent prices that reacts faster to new price
    changes than a simple average. It gives more weight to recent prices, making
    it more responsive to new information.

    Interpretation:
        - Price above EMA suggests an uptrend (bullish)
        - Price below EMA suggests a downtrend (bearish)
        - Shorter periods (e.g., 20) react faster to price changes
        - Longer periods (e.g., 200) show major trends and act as support/resistance

    Common trading uses:
        - EMA crossovers (e.g., 20 EMA crossing above 50 EMA = bullish signal)
        - Dynamic support/resistance levels
        - Trend direction confirmation

    Args:
        series: Price series (typically close prices)
        period: Number of periods for the EMA (e.g., 20, 50, 200)

    Returns:
        The most recent EMA value, or None if insufficient data
    """
    if len(series) < period:
        return None

    ema = series.ewm(span=period, adjust=False).mean()
    return Decimal(str(round(ema.iloc[-1], 8)))


def calculate_sma(series: pd.Series, period: int) -> Decimal | None:
    """
    Calculate Simple Moving Average (SMA) for the given period.

    SMA is the arithmetic mean of prices over a specified number of periods.
    It gives equal weight to all prices in the period, making it smoother
    but slower to react than EMA.

    Interpretation:
        - Price above SMA suggests bullish sentiment
        - Price below SMA suggests bearish sentiment
        - The 200-day SMA is widely watched as a major trend indicator

    Common trading uses:
        - Identifying long-term trends
        - Support and resistance levels
        - Baseline for other indicators

    Args:
        series: Price series (typically close prices)
        period: Number of periods for the SMA

    Returns:
        The most recent SMA value, or None if insufficient data
    """
    if len(series) < period:
        return None

    sma = series.rolling(window=period).mean()
    return Decimal(str(round(sma.iloc[-1], 8)))
