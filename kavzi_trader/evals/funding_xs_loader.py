import logging
from pathlib import Path

import numpy as np
import pandas as pd

from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.series_cache import TIME, VALUE, SeriesCache

logger = logging.getLogger(__name__)

UNIVERSE = tuple(
    f"{base}USDT"
    for base in (
        "BTC",
        "ETH",
        "SOL",
        "XRP",
        "BNB",
        "ADA",
        "LINK",
        "AVAX",
        "DOGE",
        "LTC",
        "DOT",
        "BCH",
        "ATOM",
        "TRX",
        "ETC",
        "FIL",
    )
)
# 2022-03-15 00:00 UTC: first rebalance and day index 0 of the pre-registration.
FIRST_MARK_MS = 1_647_302_400_000
# 2026-11-15 00:00 UTC mark, which closes 2026-11-14, the window's last day.
LAST_MARK_MS = 1_794_700_800_000
DAY_MS = 86_400_000
_CANDLE_MS = 4 * 3_600_000


class FundingXsLoader:
    """Reads daily marks and funding settlements from the eval cache."""

    def __init__(self, cache_dir: Path) -> None:
        self._candles = CandleCache(cache_dir, "4h")
        self._funding = SeriesCache(cache_dir, "funding")

    def prices(self, symbols: list[str]) -> pd.DataFrame:
        """Close of the 4h candle ending at 00:00 UTC, one row per day."""
        columns = {s: self._daily_close(s) for s in symbols}
        frame = pd.DataFrame(columns).loc[FIRST_MARK_MS:LAST_MARK_MS]
        gaps = np.diff(frame.index.to_numpy(dtype=np.int64))
        if frame.empty or (gaps != DAY_MS).any():
            msg = "daily marks are missing or not contiguous in the window"
            raise ValueError(msg)
        return frame

    def settlements(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        result = {}
        for symbol in symbols:
            frame = self._funding.load(symbol)
            if frame.empty:
                msg = f"no cached funding for {symbol}"
                raise ValueError(msg)
            result[symbol] = frame[[TIME, VALUE]]
        return result

    def _daily_close(self, symbol: str) -> pd.Series:
        candles = self._candles.load(symbol)
        if candles.empty:
            msg = f"no cached 4h candles for {symbol}"
            raise ValueError(msg)
        close_ms = candles["open_time_ms"] + _CANDLE_MS
        series = pd.Series(candles["close"].to_numpy(), index=close_ms.to_numpy())
        return series[series.index % DAY_MS == 0]
