import logging

import numpy as np
import pandas as pd

from kavzi_trader.evals.weight_signal import WeightSignal

logger = logging.getLogger(__name__)


class FundingCrowdingOverlay:
    """Halves long weights while a coin's funding sits in its own top decile.

    Crowded at close t: the mean of the last ``window_days`` daily funding sums is
    above the 90th percentile of that mean over the trailing ``history_days``,
    today included. Strictly above, because funding sits at its 0.01% baseline for
    weeks, which would tie with the percentile. Before ``min_history_days`` of
    means exist the base weights pass through unchanged.
    """

    def __init__(
        self,
        base: WeightSignal,
        funding: pd.DataFrame,
        window_days: int = 7,
        history_days: int = 365,
        min_history_days: int = 180,
        quantile: float = 0.9,
        scale: float = 0.5,
    ) -> None:
        if not 0 < quantile < 1 or not 0 <= scale <= 1:
            msg = f"need 0 < quantile < 1 and 0 <= scale <= 1, got {quantile}, {scale}"
            raise ValueError(msg)
        self._base = base
        self._funding = funding
        self._window = window_days
        self._history = history_days
        self._min_history = min_history_days
        self._quantile = quantile
        self._scale = scale

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        base = self._base.weights(closes)
        crowded = self.crowded(closes.index, list(closes.columns))
        logger.info(
            "Funding crowding flags %.1f%% of symbol-days", 100 * crowded.mean()
        )
        scaled: np.ndarray = np.where(crowded & (base > 0), base * self._scale, base)
        return scaled

    def crowded(self, days: pd.DatetimeIndex, symbols: list[str]) -> np.ndarray:
        """(days, symbols) mask of crowded closes, known at each close."""
        funding = self._funding.reindex(index=days, columns=symbols)
        mean = funding.rolling(self._window, min_periods=self._window).mean()
        threshold = mean.rolling(self._history, min_periods=self._min_history).quantile(
            self._quantile
        )
        mask: np.ndarray = (mean > threshold).to_numpy() & threshold.notna().to_numpy()
        return mask
