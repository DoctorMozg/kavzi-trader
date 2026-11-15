import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

TIME = "time_ms"
OPEN_INTEREST = "open_interest"
GLOBAL_RATIO = "global_ratio"
TOP_POSITION_RATIO = "top_position_ratio"
COLUMNS = (TIME, OPEN_INTEREST, GLOBAL_RATIO, TOP_POSITION_RATIO)


class MetricsCache:
    """Gzipped CSV of the 5-minute Binance metrics rows, one file per symbol."""

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir

    def path(self, symbol: str) -> Path:
        return self._dir / f"{symbol}_metrics_5m.csv.gz"

    def load(self, symbol: str) -> pd.DataFrame:
        path = self.path(symbol)
        if not path.exists():
            return pd.DataFrame(
                {
                    c: pd.Series(dtype="int64" if c == TIME else "float64")
                    for c in COLUMNS
                }
            )
        return pd.read_csv(path)

    def merge(self, symbol: str, rows: pd.DataFrame) -> None:
        """Add rows, dropping duplicates by time."""
        if list(rows.columns) != list(COLUMNS):
            msg = f"metrics rows for {symbol} have columns {list(rows.columns)}"
            raise ValueError(msg)
        if rows.empty:
            return
        merged = (
            pd.concat([self.load(symbol), rows], ignore_index=True)
            .drop_duplicates(TIME, keep="last")
            .sort_values(TIME)
            .reset_index(drop=True)
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self.path(symbol)
        # Write-then-rename so an interrupted run never leaves a torn file.
        tmp = path.with_name(path.name + ".tmp")
        merged.to_csv(tmp, index=False, compression="gzip")
        tmp.replace(path)
        logger.debug("Cache %s now holds %d rows", path.name, len(merged))
