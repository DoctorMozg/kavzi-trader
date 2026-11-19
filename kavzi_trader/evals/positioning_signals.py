import numpy as np
import numpy.typing as npt
import pandas as pd

from kavzi_trader.evals.metrics_alignment import MetricsAlignment
from kavzi_trader.evals.metrics_cache import GLOBAL_RATIO, TIME, TOP_POSITION_RATIO

POSITIONING_SIGNALS = ("ls_crowding", "smart_vs_crowd")
# The same thirds as taker_flow, fixed in the 2026-11-16 pre-registration.
_UPPER_RANK = 2 / 3
_LOWER_RANK = 1 / 3
MAX_RATIO_AGE_MS = 86_400_000


class PositioningSignals:
    """Long/short positioning flags from the Binance metrics archive.

    ls_crowding: global account ratio ranked within the trailing history window;
    the bottom third (crowd short) fires LONG, the top third SHORT.
    smart_vs_crowd: log(top-trader position ratio) - log(global account ratio),
    ranked the same way; top third fires LONG, bottom third SHORT.
    A bar whose latest ratio is over a day old has no rank and never fires.
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
        # NaN ranks (warm-up, stale or no metrics) compare False on every side.
        out["LONG_ls_crowding"] = crowd_rank <= _LOWER_RANK
        out["SHORT_ls_crowding"] = crowd_rank >= _UPPER_RANK
        out["LONG_smart_vs_crowd"] = smart_rank >= _UPPER_RANK
        out["SHORT_smart_vs_crowd"] = smart_rank <= _LOWER_RANK
        return out

    def crowd_rank(
        self, frame: pd.DataFrame, metrics: pd.DataFrame, lag_ms: int = 0
    ) -> npt.NDArray[np.float64]:
        """ls_crowding's rank at each bar close, from ratios ``lag_ms`` older."""
        close_ms = frame["close_time_ms"].to_numpy(dtype=np.int64) - lag_ms
        return self._rank(self._ratio_at(metrics, GLOBAL_RATIO, close_ms))

    @staticmethod
    def _ratio_at(
        metrics: pd.DataFrame, column: str, close_ms: npt.NDArray[np.int64]
    ) -> npt.NDArray[np.float64]:
        """Latest positive ratio at each close; NaN if none is under a day old."""
        valid = metrics[metrics[column] > 0]
        times = valid[TIME].to_numpy(dtype=np.int64)
        ratio = MetricsAlignment.latest_at_or_before(
            times, valid[column].to_numpy(dtype=np.float64), close_ms
        )
        seen_ms = MetricsAlignment.latest_at_or_before(
            times, times.astype(np.float64), close_ms
        )
        # Archive gaps run for months (2022, delistings); a carried ratio is not news.
        ratio[close_ms - seen_ms > MAX_RATIO_AGE_MS] = np.nan
        return ratio

    def _rank(self, values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        # Rank among the last `history` known ratios, so a gap blanks only itself.
        series = pd.Series(values)
        known = series.dropna()
        ranks = known.rolling(self._history).rank(pct=True).reindex(series.index)
        return np.asarray(ranks, dtype=np.float64)
