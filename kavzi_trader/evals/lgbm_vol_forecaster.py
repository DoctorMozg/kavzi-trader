import logging

import lightgbm
import numpy as np
import pandas as pd

from kavzi_trader.evals.har_features import DAY, TARGET, HarFeatures
from kavzi_trader.evals.monthly_refit import MonthlyRefit

logger = logging.getLogger(__name__)

LGBM_ROUNDS = 300
# Fixed before any scored run; not tuned on the evaluation window.
LGBM_PARAMS = {
    "objective": "regression",
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_data_in_leaf": 50,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "feature_fraction": 0.8,
    "seed": 20261119,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 4,
    "verbose": -1,
}


class LgbmVolForecaster:
    """Gradient-boosted log 7-day variance on HAR features, refit monthly.

    Uses LightGBM's native API, so scikit-learn is not needed.
    """

    def __init__(self, first_forecast_day: pd.Timestamp) -> None:
        self._refit = MonthlyRefit(first_forecast_day)

    @property
    def name(self) -> str:
        return "lgbm"

    def forecast(self, returns: pd.DataFrame) -> pd.DataFrame:
        panel = HarFeatures.panel(returns, extra=True)
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
            model = lightgbm.train(
                LGBM_PARAMS,
                lightgbm.Dataset(panel.loc[train, features], panel.loc[train, TARGET]),
                num_boost_round=LGBM_ROUNDS,
            )
            fitted = np.asarray(model.predict(panel.loc[train, features]))
            resid_var = float(np.var(panel.loc[train, TARGET].to_numpy() - fitted))
            month = (
                (days >= month_start)
                & (days < month_start + pd.offsets.MonthBegin(1))
                & known
            )
            if month.any():
                predicted = model.predict(panel.loc[month, features])
                out[month] = np.exp(np.asarray(predicted) + resid_var / 2)
        logger.info("lgbm: %d forecasts", int(out.notna().sum()))
        return HarFeatures.to_wide(out, returns)
