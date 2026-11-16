import logging
from pathlib import Path

import pandas as pd

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_store import ArchiveStore

logger = logging.getLogger(__name__)

SYMBOL = "symbol"
FIRST_MS = "first_trade_ms"
END_MS = "end_ms"
_BAR_MS = 60_000


class PointInTimeUniverse:
    """Which USD-M perpetuals traded when, so a backtest sees delisted ones too.

    The archive keeps zero-trade flat bars for months after a delisting, so a
    listing spans first to last bar with trades, not first to last bar.
    """

    def __init__(self, listings: pd.DataFrame) -> None:
        self._listings = listings

    @classmethod
    def from_store(cls, store: ArchiveStore) -> PointInTimeUniverse:
        klines = ARCHIVE_DATASETS["klines"]
        rows = []
        for symbol in store.symbols(klines):
            bars = store.load(klines, symbol, ["open_time_ms", "trades_count"])
            traded = bars.loc[bars["trades_count"] > 0, "open_time_ms"]
            if traded.empty:
                logger.warning("%s has stored klines but never traded", symbol)
                continue
            rows.append(
                {
                    SYMBOL: symbol,
                    FIRST_MS: int(traded.min()),
                    END_MS: int(traded.max()) + _BAR_MS,
                }
            )
        logger.info("Universe of %d symbols built from stored klines", len(rows))
        return cls(pd.DataFrame(rows, columns=[SYMBOL, FIRST_MS, END_MS]))

    @classmethod
    def load(cls, path: Path) -> PointInTimeUniverse:
        return cls(pd.read_parquet(path))

    def save(self, path: Path) -> None:
        self._listings.to_parquet(path, index=False)

    def members(self, at_ms: int) -> list[str]:
        """Symbols that had traded by ``at_ms`` and kept trading after it."""
        live = self._listings[
            (self._listings[FIRST_MS] <= at_ms) & (at_ms < self._listings[END_MS])
        ]
        return sorted(live[SYMBOL])

    def __len__(self) -> int:
        return len(self._listings)
