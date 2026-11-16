import logging
from pathlib import Path

import pandas as pd

from kavzi_trader.archive.archive_dataset_schema import ArchiveDatasetSchema

logger = logging.getLogger(__name__)


class ArchiveStore:
    """Parquet files, one per dataset, symbol and month, under one root."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path(self, dataset: ArchiveDatasetSchema, symbol: str, month: str) -> Path:
        return self._root / dataset.symbol_dir(symbol) / f"{month}.parquet"

    def has(self, dataset: ArchiveDatasetSchema, symbol: str, month: str) -> bool:
        return self.path(dataset, symbol, month).exists()

    def write(
        self,
        dataset: ArchiveDatasetSchema,
        symbol: str,
        month: str,
        rows: pd.DataFrame,
    ) -> None:
        path = self.path(dataset, symbol, month)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename: an interrupted sync never leaves a torn month,
        # and a torn month would be skipped as done on the next run.
        partial = path.with_suffix(".parquet.partial")
        rows.to_parquet(partial, index=False, compression="zstd")
        partial.replace(path)

    def load(self, dataset: ArchiveDatasetSchema, symbol: str) -> pd.DataFrame:
        """Every stored month of one symbol, oldest first."""
        files = sorted((self._root / dataset.symbol_dir(symbol)).glob("*.parquet"))
        if not files:
            return pd.DataFrame({c: [] for c in dataset.columns})
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
