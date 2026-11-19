import logging

import numpy as np
import pandas as pd

from kavzi_trader.evals.har_features import DAY, TARGET, HarFeatures
from kavzi_trader.evals.monthly_refit import MonthlyRefit

logger = logging.getLogger(__name__)


class HarVolForecaster:
    """Pooled HAR regression of log 7-day variance, refit each month on the past.

    Covariates (e.g. log DVOL variance) enter as extra regressors; rows without
    them are neither fit nor forecast.
    """

    def __init__(
        self,
        first_forecast_day: pd.Timestamp,
        covariates: dict[str, pd.DataFrame] | None = None,
        label: str = "har",
    ) -> None:
        self._refit = MonthlyRefit(first_forecast_day)
        self._covariates = covariates
        self._label = label

    @property
    def name(self) -> str:
        return self._label

    def forecast(self, returns: pd.DataFrame) -> pd.DataFrame:
        panel = HarFeatures.panel(returns, self._covariates)
        features = HarFeatures.feature_names(panel)
        known = panel[features].notna().all(axis=1)
        days = pd.Series(panel.index.get_level_values(DAY), index=panel.index)
        out = pd.Series(np.nan, index=panel.index)
        for month_start, _ in self._refit.months(returns.index):
            train = (
                known
                & panel[TARGET].notna()
                & MonthlyRefit.train_mask(days, month_start)
            )
            design = np.column_stack([np.ones(train.sum()), panel.loc[train, features]])
            target = panel.loc[train, TARGET].to_numpy()
            beta, *_ = np.linalg.lstsq(design, target, rcond=None)
            resid_var = float(np.var(target - design @ beta))
            month = (
                (days >= month_start)
                & (days < month_start + pd.offsets.MonthBegin(1))
                & known
            )
            rows = np.column_stack([np.ones(month.sum()), panel.loc[month, features]])
            # exp of a log-normal mean: E[v] = exp(mu + s^2 / 2).
            out[month] = np.exp(rows @ beta + resid_var / 2)
        logger.info("%s: %d forecasts", self._label, int(out.notna().sum()))
        return HarFeatures.to_wide(out, returns)
