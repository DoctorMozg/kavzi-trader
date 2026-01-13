import pandas as pd

from kavzi_trader.api.common.models import CandlestickSchema


def candles_to_dataframe(candles: list[CandlestickSchema]) -> pd.DataFrame:
    """
    Convert CandlestickSchema list to pandas DataFrame for indicator calculations.

    The DataFrame uses OHLCV column names expected by technical analysis functions:
    - open, high, low, close, volume
    - Indexed by open_time for time-series operations

    Args:
        candles: List of candlestick data from the exchange

    Returns:
        DataFrame with OHLCV data indexed by timestamp
    """
    if not candles:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "quote_volume"],
        )

    data = [
        {
            "open_time": c.open_time,
            "open": float(c.open_price),
            "high": float(c.high_price),
            "low": float(c.low_price),
            "close": float(c.close_price),
            "volume": float(c.volume),
            "quote_volume": float(c.quote_volume),
        }
        for c in candles
    ]

    ohlcv = pd.DataFrame(data)
    ohlcv = ohlcv.set_index("open_time")
    return ohlcv.sort_index()
