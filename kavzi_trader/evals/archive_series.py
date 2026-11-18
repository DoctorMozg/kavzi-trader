import logging
from pathlib import Path

import pandas as pd

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.evals.candle_cache import COLUMNS
from kavzi_trader.evals.metrics_cache import COLUMNS as METRICS_COLUMNS
from kavzi_trader.evals.series_cache import TIME, VALUE

logger = logging.getLogger(__name__)

_S_PER_DAY = 86_400
_MS_PER_S = 1000
_SUMMED = [
    "volume",
    "quote_volume",
    "trades_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
]


class ArchiveSeries:
    """Reads the mirrored archive in the shapes the eval caches use."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._store = ArchiveStore(root)

    def candles(self, symbol: str, interval: str) -> pd.DataFrame:
        """1m klines rolled up to ``interval`` bars, sorted by open time."""
        seconds = KLINE_INTERVALS.get(interval)
        # Longer bars, e.g. Binance's Monday-anchored 1w, don't start at UTC midnight.
        if seconds is None or _S_PER_DAY % seconds:
            msg = f"interval {interval!r} does not divide a UTC day"
            raise ValueError(msg)
        minutes = self._store.load(ARCHIVE_DATASETS["klines"], symbol)
        if minutes.empty:
            msg = (
                f"no archived 1m klines for {symbol} under {self._root}; run "
                f"`kavzitrader eval archive --symbols {symbol} --root {self._root}`"
            )
            raise FileNotFoundError(msg)
        bar_ms = seconds * _MS_PER_S
        start = minutes["open_time_ms"] // bar_ms * bar_ms
        grouped = minutes.sort_values("open_time_ms").groupby(start)
        bars = grouped.agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            **{c: (c, "sum") for c in _SUMMED},
        )
        bars["open_time_ms"] = bars.index
        bars["close_time_ms"] = bars.index + bar_ms - 1
        logger.debug("%s: %d %s bars from archive", symbol, len(bars), interval)
        return bars[list(COLUMNS)].reset_index(drop=True)

    def daily_bars(self, symbol: str) -> pd.DataFrame:
        """Binance's own 1d klines, sorted; empty when none are stored."""
        bars = self._store.load(ARCHIVE_DATASETS["klines_1d"], symbol)
        return bars.sort_values("open_time_ms", ignore_index=True)

    def funding(self, symbol: str) -> pd.DataFrame:
        """Funding settlements as ``time_ms`` and the rate ``value``."""
        rows = self._store.load(ARCHIVE_DATASETS["funding"], symbol, [TIME, "rate"])
        return (
            rows.rename(columns={"rate": VALUE})
            .astype({TIME: "int64", VALUE: "float64"})
            .sort_values(TIME, ignore_index=True)
        )

    def metrics(self, symbol: str) -> pd.DataFrame:
        """5-minute open interest and long/short ratios, sorted by time."""
        rows = self._store.load(
            ARCHIVE_DATASETS["metrics"], symbol, list(METRICS_COLUMNS)
        )
        return rows.astype({TIME: "int64"}).sort_values(TIME, ignore_index=True)
