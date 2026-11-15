import numpy as np
import numpy.typing as npt
import pandas as pd

from kavzi_trader.evals.metrics_alignment import MetricsAlignment
from kavzi_trader.evals.metrics_cache import GLOBAL_RATIO, TIME, TOP_POSITION_RATIO

POSITIONING_SIGNALS = ("ls_crowding", "smart_vs_crowd")
# The same thirds as taker_flow, fixed in the 2026-11-16 pre-registration.
_UPPER_RANK = 2 / 3
_LOWER_RANK = 1 / 3


class PositioningSignals:
    """Long/short positioning flags from the Binance metrics archive.

    ls_crowding: global account ratio ranked within the trailing history window;
    the bottom third (crowd short) fires LONG, the top third SHORT.
    smart_vs_crowd: log(top-trader position ratio) - log(global account ratio),
    ranked the same way; top third fires LONG, bottom third SHORT.
    """

    def __init__(self, history: int) -> None:
        self._history = history

    def add(
        self, frame: pd.DataFrame, samples: pd.DataFrame, metrics: pd.DataFrame
    ) -> pd.DataFrame:
        """``samples`` plus LONG_/SHORT_ columns for each positioning signal."""
        if samples.empty:
            return samples
        close_ms = frame["close_time_ms"].to_numpy(dtype=np.int64)
        crowd = self._ratio_at(metrics, GLOBAL_RATIO, close_ms)
        top = self._ratio_at(metrics, TOP_POSITION_RATIO, close_ms)
        idx = samples["idx"].to_numpy(dtype=np.int64)
        out = samples.copy()
        crowd_rank = self._rank(crowd)[idx]
        smart_rank = self._rank(np.log(top) - np.log(crowd))[idx]
        # NaN ranks (warm-up, no metrics yet) compare False on every side.
        out["LONG_ls_crowding"] = crowd_rank <= _LOWER_RANK
        out["SHORT_ls_crowding"] = crowd_rank >= _UPPER_RANK
        out["LONG_smart_vs_crowd"] = smart_rank >= _UPPER_RANK
        out["SHORT_smart_vs_crowd"] = smart_rank <= _LOWER_RANK
        return out

    @staticmethod
    def _ratio_at(
        metrics: pd.DataFrame, column: str, close_ms: npt.NDArray[np.int64]
    ) -> npt.NDArray[np.float64]:
        """Latest positive ratio at each close, skipping the archive's empty rows."""
        valid = metrics[metrics[column] > 0]
        return MetricsAlignment.latest_at_or_before(
            valid[TIME].to_numpy(dtype=np.int64),
            valid[column].to_numpy(dtype=np.float64),
            close_ms,
        )

    def _rank(self, values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        ranks = pd.Series(values).rolling(self._history).rank(pct=True)
        return np.asarray(ranks, dtype=np.float64)
