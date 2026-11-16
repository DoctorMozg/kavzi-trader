import math
from statistics import NormalDist

import numpy as np
import pandas as pd

from kavzi_trader.evals.validation.deflated_sharpe_schema import DeflatedSharpeSchema

EULER_GAMMA = 0.5772156649015329
_NORMAL = NormalDist()
_MIN_OBS = 3


class SharpeDeflation:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014), per-period units."""

    @staticmethod
    def probabilistic_sharpe(
        sharpe: float,
        benchmark: float,
        n_obs: int,
        skew: float,
        kurtosis: float,
    ) -> float:
        """P(true Sharpe > benchmark); kurtosis is raw, 3 for Normal returns."""
        if n_obs < _MIN_OBS:
            msg = f"need at least {_MIN_OBS} observations, got {n_obs}"
            raise ValueError(msg)
        spread = 1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe**2
        if spread <= 0:
            msg = f"non-positive Sharpe variance for skew {skew}, kurtosis {kurtosis}"
            raise ValueError(msg)
        z = (sharpe - benchmark) * math.sqrt(n_obs - 1) / math.sqrt(spread)
        return _NORMAL.cdf(z)

    @staticmethod
    def expected_max_sharpe(n_trials: int, sharpe_variance: float) -> float:
        """Expected best Sharpe of n_trials independent zero-skill trials."""
        if n_trials < 1 or sharpe_variance < 0:
            msg = f"bad trials {n_trials} or variance {sharpe_variance}"
            raise ValueError(msg)
        if n_trials == 1:
            return 0.0
        quantiles = (1 - EULER_GAMMA) * _NORMAL.inv_cdf(
            1 - 1 / n_trials
        ) + EULER_GAMMA * _NORMAL.inv_cdf(1 - 1 / (n_trials * math.e))
        return math.sqrt(sharpe_variance) * quantiles

    def deflate(
        self, returns: pd.Series, trial_sharpes: list[float]
    ) -> DeflatedSharpeSchema:
        """Deflates the chosen strategy's returns by every trial tried, itself included.

        Trial Sharpes are per period; their sample variance stands in for V[SR].
        """
        clean = returns.dropna()
        if len(clean) < _MIN_OBS or clean.nunique() < 2:  # noqa: PLR2004
            msg = f"need {_MIN_OBS}+ non-constant returns, got {len(clean)}"
            raise ValueError(msg)
        if not trial_sharpes:
            msg = "trial_sharpes must include at least the selected strategy"
            raise ValueError(msg)
        sharpe = float(clean.mean() / clean.std())
        variance = (
            float(np.var(trial_sharpes, ddof=1)) if len(trial_sharpes) > 1 else 0.0
        )
        threshold = self.expected_max_sharpe(len(trial_sharpes), variance)
        deflated = self.probabilistic_sharpe(
            sharpe,
            threshold,
            len(clean),
            float(clean.skew()),
            # pandas gives excess kurtosis; the formula wants raw.
            float(clean.kurt()) + 3,
        )
        return DeflatedSharpeSchema(
            sharpe=sharpe,
            expected_max_sharpe=threshold,
            deflated_sharpe=deflated,
            n_trials=len(trial_sharpes),
            n_obs=len(clean),
        )
