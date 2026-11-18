from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.candle_cache import COLUMNS
from kavzi_trader.evals.trend_data_loader import TrendDataLoader

DAY_MS = 86_400_000
FIRST_MS = 1_640_995_200_000  # 2022-01-01


def _daily(closes: list[float], first_ms: int = FIRST_MS) -> pd.DataFrame:
    open_ms = first_ms + np.arange(len(closes)) * DAY_MS
    return pd.DataFrame(
        {
            "open_time_ms": open_ms,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": 1.0,
            "close_time_ms": open_ms + DAY_MS - 1,
            "quote_volume": 1.0,
            "trades_count": 1,
            "taker_buy_base_volume": 0.5,
            "taker_buy_quote_volume": 0.5,
        },
        columns=list(COLUMNS),
    )


@pytest.fixture
def store(tmp_path: Path) -> ArchiveStore:
    return ArchiveStore(tmp_path)


@pytest.fixture
def loader(tmp_path: Path) -> TrendDataLoader:
    return TrendDataLoader(ArchiveSeries(tmp_path))


class TestDailyBars:
    def test_a_delisted_symbol_leaves_nan_after_its_last_close(
        self, store: ArchiveStore, loader: TrendDataLoader
    ) -> None:
        daily = ARCHIVE_DATASETS["klines_1d"]
        store.write(daily, "LIVE", "2022-01", _daily([1, 2, 3, 4, 5]))
        store.write(daily, "GONE", "2022-01", _daily([9, 8, 7]))

        closes = loader.load(["LIVE", "GONE"]).closes

        assert closes.index[0] == pd.Timestamp("2022-01-01")
        assert closes["LIVE"].tolist() == [1, 2, 3, 4, 5]
        assert closes["GONE"].tolist()[:3] == [9, 8, 7]
        assert closes["GONE"].iloc[3:].isna().all()

    def test_a_missing_day_inside_the_history_is_an_error(
        self, store: ArchiveStore, loader: TrendDataLoader
    ) -> None:
        bars = _daily([1, 2, 3, 4]).drop(index=2)
        store.write(ARCHIVE_DATASETS["klines_1d"], "HOLE", "2022-01", bars)

        with pytest.raises(ValueError, match="HOLE has 1 missing daily bars"):
            loader.load(["HOLE"])
