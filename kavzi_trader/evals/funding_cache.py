import logging
from pathlib import Path

import pandas as pd

from kavzi_trader.api.binance.schemas.data_dicts import FundingRateDict

logger = logging.getLogger(__name__)

COLUMNS = ("funding_time_ms", "funding_rate")


class FundingCache:
    """Gzipped CSV of futures funding settlements, one file per symbol."""

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir

    def path(self, symbol: str) -> Path:
        return self._dir / f"{symbol}_funding.csv.gz"

    def load(self, symbol: str) -> pd.DataFrame:
        path = self.path(symbol)
        if not path.exists():
            return pd.DataFrame(
                {"funding_time_ms": pd.Series(dtype="int64"),
                 "funding_rate": pd.Series(dtype="float64")}
            )  # fmt: skip
        return pd.read_csv(
            path, dtype={"funding_time_ms": "int64", "funding_rate": "float64"}
        )

    def merge(self, symbol: str, rates: list[FundingRateDict]) -> None:
        """Add settlements, dropping duplicates by funding time."""
        if not rates:
            return
        fresh = pd.DataFrame(
            {
                "funding_time_ms": [int(r["fundingTime"]) for r in rates],
                "funding_rate": [float(r["fundingRate"]) for r in rates],
            }
        )
        merged = (
            pd.concat([self.load(symbol), fresh], ignore_index=True)
            .drop_duplicates("funding_time_ms", keep="last")
            .sort_values("funding_time_ms")
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self.path(symbol)
        # Write-then-rename so an interrupted run never leaves a torn file.
        tmp = path.with_name(path.name + ".tmp")
        merged.to_csv(tmp, index=False, compression="gzip")
        tmp.replace(path)
        logger.debug("Cache %s now holds %d settlements", path.name, len(merged))
