from decimal import Decimal

import pandas as pd

from kavzi_trader.indicators.schemas import MACDResultSchema


def calculate_rsi(series: pd.Series, period: int = 14) -> Decimal | None:
    """
    Calculate Relative Strength Index (RSI).

    RSI measures if an asset is "overbought" (price rose too fast, may drop)
    or "oversold" (price fell too fast, may rise). It oscillates between 0 and 100.

    Interpretation:
        - RSI > 70: Overbought - price may be due for a pullback
        - RSI < 30: Oversold - price may be due for a bounce
        - RSI = 50: Neutral momentum

    Common trading uses:
        - Identifying potential reversal points
        - Confirming trend strength (RSI staying above 50 = strong uptrend)
        - Divergence trading (price makes new high but RSI doesn't = weakness)

    Args:
        series: Price series (typically close prices)
        period: RSI period (default 14, the standard)

    Returns:
        RSI value between 0 and 100, or None if insufficient data
    """
    if len(series) < period + 1:
        return None

    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    # Drop leading NaN from diff()
    gain_vals = gain.dropna().to_numpy()
    loss_vals = loss.dropna().to_numpy()

    alpha = 1.0 / period

    # Wilder smoothing: seed with SMA of first `period` values
    avg_gain = float(gain_vals[:period].mean())
    avg_loss = float(loss_vals[:period].mean())

    for i in range(period, len(gain_vals)):
        avg_gain = avg_gain * (1 - alpha) + float(gain_vals[i]) * alpha
        avg_loss = avg_loss * (1 - alpha) + float(loss_vals[i]) * alpha

    if avg_loss == 0:
        return Decimal(100) if avg_gain > 0 else Decimal(0)

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return Decimal(str(round(rsi, 2)))


def calculate_macd(
    series: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MACDResultSchema | None:
    """
    Calculate Moving Average Convergence Divergence (MACD).

    MACD shows momentum by comparing fast and slow moving averages. It helps
    identify trend direction and momentum strength.

    Components:
        - MACD Line: Difference between fast EMA (12) and slow EMA (26)
        - Signal Line: 9-period EMA of the MACD line
        - Histogram: MACD Line minus Signal Line (shows momentum strength)

    Interpretation:
        - MACD crosses above Signal = bullish momentum (buy signal)
        - MACD crosses below Signal = bearish momentum (sell signal)
        - Histogram growing = momentum increasing
        - Histogram shrinking = momentum fading

    Common trading uses:
        - Trend direction confirmation
        - Entry/exit timing via crossovers
        - Divergence trading (price vs MACD disagreement)

    Args:
        series: Price series (typically close prices)
        fast_period: Fast EMA period (default 12)
        slow_period: Slow EMA period (default 26)
        signal_period: Signal line EMA period (default 9)

    Returns:
        MACDResultSchema with macd_line, signal_line, and histogram values
    """
    if len(series) < slow_period + signal_period:
        return None

    fast_ema = series.ewm(span=fast_period, adjust=False).mean()
    slow_ema = series.ewm(span=slow_period, adjust=False).mean()

    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    return MACDResultSchema(
        macd_line=Decimal(str(round(macd_line.iloc[-1], 8))),
        signal_line=Decimal(str(round(signal_line.iloc[-1], 8))),
        histogram=Decimal(str(round(histogram.iloc[-1], 8))),
    )
