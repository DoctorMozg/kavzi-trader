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

    def load(
        self,
        dataset: ArchiveDatasetSchema,
        symbol: str,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """Every stored month of one symbol, oldest first."""
        wanted = columns or dataset.columns
        files = sorted((self._root / dataset.symbol_dir(symbol)).glob("*.parquet"))
        if not files:
            return pd.DataFrame({c: [] for c in wanted})
        parts = [pd.read_parquet(f, columns=wanted) for f in files]
        return pd.concat(parts, ignore_index=True)

    def symbols(self, dataset: ArchiveDatasetSchema) -> list[str]:
        """Symbols with at least one stored month of the dataset."""
        base = self._root / dataset.name
        if not base.is_dir():
            return []
        return sorted(d.name for d in base.iterdir() if self.months(dataset, d.name))

    def months(self, dataset: ArchiveDatasetSchema, symbol: str) -> list[str]:
        folder = self._root / dataset.symbol_dir(symbol)
        return sorted(f.stem for f in folder.glob("*.parquet"))
