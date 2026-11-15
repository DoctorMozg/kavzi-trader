import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

TIME = "time_ms"
VALUE = "value"


class SeriesCache:
    """Gzipped CSV of one timestamped value per row, one file per symbol.

    Holds the exchange histories that are not candles, e.g. funding settlements
    or open interest snapshots, keyed by ``name`` in the file name.
    """

    def __init__(self, cache_dir: Path, name: str) -> None:
        self._dir = cache_dir
        self._name = name

    def path(self, symbol: str) -> Path:
        return self._dir / f"{symbol}_{self._name}.csv.gz"

    def load(self, symbol: str) -> pd.DataFrame:
        path = self.path(symbol)
        if not path.exists():
            return pd.DataFrame(
                {TIME: pd.Series(dtype="int64"), VALUE: pd.Series(dtype="float64")}
            )
        return pd.read_csv(path, dtype={TIME: "int64", VALUE: "float64"})

    def merge(self, symbol: str, times_ms: list[int], values: list[float]) -> None:
        """Add rows, dropping duplicates by time."""
        if len(times_ms) != len(values):
            msg = f"{len(times_ms)} times but {len(values)} values for {symbol}"
            raise ValueError(msg)
        if not times_ms:
            return
        fresh = pd.DataFrame({TIME: times_ms, VALUE: values})
        merged = (
            pd.concat([self.load(symbol), fresh], ignore_index=True)
            .drop_duplicates(TIME, keep="last")
            .sort_values(TIME)
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self.path(symbol)
        # Write-then-rename so an interrupted run never leaves a torn file.
        tmp = path.with_name(path.name + ".tmp")
        merged.to_csv(tmp, index=False, compression="gzip")
        tmp.replace(path)
        logger.debug("Cache %s now holds %d rows", path.name, len(merged))
