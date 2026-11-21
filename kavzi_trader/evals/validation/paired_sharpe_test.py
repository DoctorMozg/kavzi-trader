import numpy as np

from kavzi_trader.evals.validation.paired_sharpe_schema import PairedSharpeSchema
from kavzi_trader.strategies.trend.donchian_trend_signal import DAYS_PER_YEAR

# Fixed so a preregistered run is reproducible.
BOOTSTRAP_SEED = 20261119
_MIN_DAYS = 30


class PairedSharpeTest:
    """Stationary block bootstrap of the annualised Sharpe difference of two series.

    Both series are resampled with the same day indices, so their correlation and
    autocorrelation survive the resampling.
    """

    def __init__(
        self,
        resamples: int = 5000,
        mean_block_days: int = 20,
        seed: int = BOOTSTRAP_SEED,
        confidence: float = 0.90,
    ) -> None:
        if not 0 < confidence < 1:
            msg = f"confidence must be in (0, 1), got {confidence}"
            raise ValueError(msg)
        if resamples < 1 or mean_block_days < 1:
            msg = (
                f"need positive resamples and block, got {resamples}, {mean_block_days}"
            )
            raise ValueError(msg)
        self._resamples = resamples
        self._block = mean_block_days
        self._seed = seed
        self._confidence = confidence

    def compare(self, base: list[float], arm: list[float]) -> PairedSharpeSchema:
        base_arr, arm_arr = np.asarray(base, float), np.asarray(arm, float)
        if base_arr.shape != arm_arr.shape or len(base_arr) < _MIN_DAYS:
            msg = (
                f"need two aligned series of at least {_MIN_DAYS} days, got "
                f"{base_arr.shape} and {arm_arr.shape}"
            )
            raise ValueError(msg)
        idx = self._indices(len(base_arr))
        diffs = self._sharpe(arm_arr[idx]) - self._sharpe(base_arr[idx])
        base_sharpe = float(self._sharpe(base_arr[None, :])[0])
        arm_sharpe = float(self._sharpe(arm_arr[None, :])[0])
        # Rounded so 0.90 gives exactly the 5th and 95th percentiles.
        tail = round(50 * (1.0 - self._confidence), 10)
        return PairedSharpeSchema(
            base_sharpe=base_sharpe,
            arm_sharpe=arm_sharpe,
            difference=arm_sharpe - base_sharpe,
            lower=float(np.percentile(diffs, tail)),
            upper=float(np.percentile(diffs, 100 - tail)),
            p_not_better=float((diffs <= 0).mean()),
            resamples=self._resamples,
            mean_block_days=self._block,
            confidence=self._confidence,
        )

    def _indices(self, n_days: int) -> np.ndarray:
        rng = np.random.default_rng(self._seed)
        idx = np.empty((self._resamples, n_days), dtype=np.int64)
        idx[:, 0] = rng.integers(0, n_days, self._resamples)
        restart = rng.random((self._resamples, n_days)) < 1.0 / self._block
        fresh = rng.integers(0, n_days, (self._resamples, n_days))
        for t in range(1, n_days):
            idx[:, t] = np.where(
                restart[:, t], fresh[:, t], (idx[:, t - 1] + 1) % n_days
            )
        return idx

    @staticmethod
    def _sharpe(returns: np.ndarray) -> np.ndarray:
        std = returns.std(axis=1, ddof=1)
        mean = returns.mean(axis=1)
        sharpe: np.ndarray = np.where(
            std > 0, mean / np.where(std > 0, std, 1.0), 0.0
        ) * np.sqrt(DAYS_PER_YEAR)
        return sharpe
