import logging

import numpy as np
import pandas as pd

from kavzi_trader.evals.validation.backtest_overfitting import BacktestOverfitting
from kavzi_trader.evals.validation.sharpe_deflation import SharpeDeflation
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.evals.validation.trial_summary_schema import TrialSummarySchema

logger = logging.getLogger(__name__)


class TrialAnalyzer:
    """Deflates a family's best trial by all its trials and estimates its PBO."""

    def __init__(
        self, deflation: SharpeDeflation, overfitting: BacktestOverfitting
    ) -> None:
        self._deflation = deflation
        self._overfitting = overfitting

    def summarize(self, trials: list[TrialSchema]) -> TrialSummarySchema:
        if not trials:
            msg = "no trials to summarize"
            raise ValueError(msg)
        sharpes = [_sharpe(t) for t in trials]
        best = trials[int(np.argmax(sharpes))]
        deflated = self._deflation.deflate(pd.Series(best.daily_net), sharpes)
        # PBO ranks variants on the same days, so only same-window trials count.
        peers = [
            t
            for t in trials
            if (t.first_day, t.last_day) == (best.first_day, best.last_day)
        ]
        pbo = None
        if len(peers) > 1:
            matrix = np.column_stack([t.daily_net for t in peers])
            pbo = self._overfitting.probability(matrix)
        else:
            logger.info(
                "PBO needs two trials over %s..%s", best.first_day, best.last_day
            )
        return TrialSummarySchema(
            family=best.family,
            n_trials=len(trials),
            best_variant=best.variant,
            deflated=deflated,
            pbo=pbo,
            pbo_trials=len(peers) if pbo is not None else 0,
        )


def _sharpe(trial: TrialSchema) -> float:
    returns = np.asarray(trial.daily_net)
    std = returns.std(ddof=1)
    return float(returns.mean() / std) if std > 0 else 0.0
