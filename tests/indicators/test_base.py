from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.base import candles_to_dataframe


def test_candles_to_dataframe_empty() -> None:
    ohlcv = candles_to_dataframe([])
    assert ohlcv.empty
    assert "open" in ohlcv.columns
    assert "close" in ohlcv.columns


def test_candles_to_dataframe_converts_correctly(
    sample_candles: list[CandlestickSchema],
) -> None:
    ohlcv = candles_to_dataframe(sample_candles)

    assert len(ohlcv) == len(sample_candles)
    assert list(ohlcv.columns) == [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
    ]

    assert ohlcv.index.name == "open_time"
    assert ohlcv.index.is_monotonic_increasing

    first_candle = sample_candles[0]
    assert ohlcv.iloc[0]["open"] == float(first_candle.open_price)
    assert ohlcv.iloc[0]["close"] == float(first_candle.close_price)


def test_candles_to_dataframe_sorts_by_time(
    sample_candles: list[CandlestickSchema],
) -> None:
    reversed_candles = list(reversed(sample_candles))
    ohlcv = candles_to_dataframe(reversed_candles)

    assert ohlcv.index.is_monotonic_increasing
