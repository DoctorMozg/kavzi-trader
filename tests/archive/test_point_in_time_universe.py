from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.archive.point_in_time_universe import PointInTimeUniverse
from kavzi_trader.evals.candle_cache import COLUMNS

KLINES = ARCHIVE_DATASETS["klines"]
MINUTE_MS = 60_000


def _bars(first_ms: int, trades: list[int]) -> pd.DataFrame:
    open_ms = first_ms + np.arange(len(trades)) * MINUTE_MS
    frame = pd.DataFrame(dict.fromkeys(COLUMNS, 1.0), index=range(len(trades)))
    frame["open_time_ms"] = open_ms
    frame["close_time_ms"] = open_ms + MINUTE_MS - 1
    frame["trades_count"] = trades
    return frame


@pytest.fixture
def universe(tmp_path: Path) -> PointInTimeUniverse:
    store = ArchiveStore(tmp_path)
    # Delisted after its third bar; the archive keeps flat zero-trade bars.
    store.write(KLINES, "OLDUSDT", "2020-01", _bars(0, [5, 5, 5, 0, 0, 0]))
    store.write(KLINES, "NEWUSDT", "2020-01", _bars(2 * MINUTE_MS, [0, 3, 3, 3, 3]))
    store.write(KLINES, "DEADUSDT", "2020-01", _bars(0, [0, 0]))
    return PointInTimeUniverse.from_store(store)


class TestPointInTimeUniverse:
    @pytest.mark.parametrize(
        ("minute", "members"),
        [
            (0, ["OLDUSDT"]),
            (2, ["OLDUSDT"]),
            (3, ["NEWUSDT"]),
            (6, ["NEWUSDT"]),
            (7, []),
        ],
    )
    def test_members_span_first_to_last_traded_bar(
        self, universe: PointInTimeUniverse, minute: int, members: list[str]
    ) -> None:
        assert universe.members(minute * MINUTE_MS) == members

    def test_a_symbol_that_never_traded_is_left_out(
        self, universe: PointInTimeUniverse
    ) -> None:
        assert len(universe) == 2

    def test_survives_a_save_and_load(
        self, universe: PointInTimeUniverse, tmp_path: Path
    ) -> None:
        universe.save(tmp_path / "universe.parquet")

        loaded = PointInTimeUniverse.load(tmp_path / "universe.parquet")

        assert loaded.members(3 * MINUTE_MS) == ["NEWUSDT"]
