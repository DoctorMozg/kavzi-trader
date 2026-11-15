import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.metrics_cache import (
    GLOBAL_RATIO,
    OPEN_INTEREST,
    TIME,
    TOP_POSITION_RATIO,
)
from kavzi_trader.evals.positioning_signals import PositioningSignals
from tests.evals.frames import make_frame

HISTORY = 200
CROWD_SHORT_BAR = HISTORY + 3
CROWD_LONG_BAR = HISTORY + 13


def _metrics(frame: pd.DataFrame, crowd: np.ndarray, top: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            # A row one second before each close, as the archive would have it.
            TIME: frame["close_time_ms"].to_numpy() - 1000,
            OPEN_INTEREST: 1.0,
            GLOBAL_RATIO: crowd,
            TOP_POSITION_RATIO: top,
        }
    )


def _samples(*idx: int) -> pd.DataFrame:
    return pd.DataFrame({"symbol": "ETHUSDT", "idx": list(idx)})


@pytest.fixture
def frame() -> pd.DataFrame:
    return make_frame(HISTORY + 30)


@pytest.fixture
def crowd(frame: pd.DataFrame) -> np.ndarray:
    ratio = np.random.default_rng(3).uniform(1.0, 2.0, len(frame))
    ratio[CROWD_SHORT_BAR] = 0.2
    ratio[CROWD_LONG_BAR] = 9.0
    return ratio


class TestLsCrowding:
    def test_short_crowd_fires_long_and_long_crowd_fires_short(
        self, frame: pd.DataFrame, crowd: np.ndarray
    ) -> None:
        metrics = _metrics(frame, crowd, np.ones(len(frame)))

        out = PositioningSignals(HISTORY).add(
            frame, _samples(CROWD_SHORT_BAR, CROWD_LONG_BAR), metrics
        )

        assert out["LONG_ls_crowding"].tolist() == [True, False]
        assert out["SHORT_ls_crowding"].tolist() == [False, True]

    def test_thresholds_are_the_outer_thirds(self, frame: pd.DataFrame) -> None:
        # Ratios rise with the bar index, so the rank of bar i in a window that
        # ends at i is 1.0: only the SHORT side fires, never the middle.
        rising = np.linspace(1.0, 2.0, len(frame))
        metrics = _metrics(frame, rising, np.ones(len(frame)))

        out = PositioningSignals(HISTORY).add(frame, _samples(HISTORY + 5), metrics)

        assert out["SHORT_ls_crowding"].tolist() == [True]
        assert out["LONG_ls_crowding"].tolist() == [False]

    def test_later_row_does_not_leak_into_an_earlier_bar(
        self, frame: pd.DataFrame, crowd: np.ndarray
    ) -> None:
        metrics = _metrics(frame, crowd, np.ones(len(frame)))
        after_close = int(frame["close_time_ms"].iloc[CROWD_SHORT_BAR]) + 1
        leak = pd.DataFrame(
            {
                TIME: [after_close],
                OPEN_INTEREST: [1.0],
                GLOBAL_RATIO: [99.0],
                TOP_POSITION_RATIO: [1.0],
            }
        )
        both = pd.concat([metrics, leak]).sort_values(TIME, ignore_index=True)

        out = PositioningSignals(HISTORY).add(frame, _samples(CROWD_SHORT_BAR), both)

        assert out["LONG_ls_crowding"].tolist() == [True]

    def test_warm_up_and_missing_metrics_never_fire(self, frame: pd.DataFrame) -> None:
        empty = pd.DataFrame(
            {c: pd.Series(dtype="float64") for c in (TIME, GLOBAL_RATIO)}
        )
        empty[TOP_POSITION_RATIO] = pd.Series(dtype="float64")

        out = PositioningSignals(HISTORY).add(frame, _samples(10, HISTORY + 5), empty)

        for column in out.filter(regex="ls_crowding|smart_vs_crowd"):
            assert not out[column].any()


class TestSmartVsCrowd:
    def test_top_traders_long_against_a_short_crowd_fires_long(
        self, frame: pd.DataFrame, crowd: np.ndarray
    ) -> None:
        # Constant top ratio: log(top) - log(crowd) is highest where the crowd
        # ratio is lowest, and lowest where it is highest.
        metrics = _metrics(frame, crowd, np.ones(len(frame)))

        out = PositioningSignals(HISTORY).add(
            frame, _samples(CROWD_SHORT_BAR, CROWD_LONG_BAR), metrics
        )

        assert out["LONG_smart_vs_crowd"].tolist() == [True, False]
        assert out["SHORT_smart_vs_crowd"].tolist() == [False, True]

    def test_empty_row_falls_back_to_the_last_usable_ratio(
        self, frame: pd.DataFrame, crowd: np.ndarray
    ) -> None:
        crowd[CROWD_SHORT_BAR - 1] = 0.2
        crowd[CROWD_SHORT_BAR] = np.nan
        metrics = _metrics(frame, crowd, np.ones(len(frame)))

        out = PositioningSignals(HISTORY).add(frame, _samples(CROWD_SHORT_BAR), metrics)

        assert out["LONG_ls_crowding"].tolist() == [True]
        assert out["LONG_smart_vs_crowd"].tolist() == [True]
