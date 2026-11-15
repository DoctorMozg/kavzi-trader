import numpy as np
import numpy.typing as npt
import pandas as pd

from kavzi_trader.evals.metrics_cache import OPEN_INTEREST, TIME
from kavzi_trader.evals.series_cache import TIME as SERIES_TIME
from kavzi_trader.evals.series_cache import VALUE


class MetricsAlignment:
    """Look-ahead-free views of the 5-minute metrics rows."""

    @staticmethod
    def latest_at_or_before(
        times_ms: npt.NDArray[np.int64],
        values: npt.NDArray[np.float64],
        at_ms: npt.NDArray[np.int64],
    ) -> npt.NDArray[np.float64]:
        """Value of the latest row with time <= each ``at_ms``; NaN before the first."""
        pos = np.searchsorted(times_ms, at_ms, side="right") - 1
        out = np.full(len(at_ms), np.nan)
        known = pos >= 0
        out[known] = values[pos[known]]
        return out

    @classmethod
    def oi_grid(cls, metrics: pd.DataFrame, period_ms: int) -> pd.DataFrame:
        """Open interest on the ``period_ms`` grid the live calculator indexes by."""
        rows = metrics.dropna(subset=[OPEN_INTEREST])
        if rows.empty:
            return pd.DataFrame(
                {
                    SERIES_TIME: pd.Series(dtype="int64"),
                    VALUE: pd.Series(dtype="float64"),
                }
            )
        times = rows[TIME].to_numpy(dtype=np.int64)
        first = -(-int(times[0]) // period_ms) * period_ms
        grid = np.arange(first, int(times[-1]) + 1, period_ms, dtype=np.int64)
        values = cls.latest_at_or_before(
            times, rows[OPEN_INTEREST].to_numpy(dtype=np.float64), grid
        )
        return pd.DataFrame({SERIES_TIME: grid, VALUE: values})
