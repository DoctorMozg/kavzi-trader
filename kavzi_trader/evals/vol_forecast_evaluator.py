import math

import numpy as np
import pandas as pd

from kavzi_trader.evals.vol_forecast_score_schema import VolForecastScoreSchema

# The 7-day targets overlap, so loss differentials autocorrelate for about 6 days.
NEWEY_WEST_LAG = 7


class VolForecastEvaluator:
    """QLIKE loss of variance forecasts and a Diebold-Mariano test per forecaster."""

    def __init__(self, realized: pd.DataFrame, days: pd.DatetimeIndex) -> None:
        self._realized = realized
        self._days = days

    def score(
        self,
        forecast: pd.DataFrame,
        baseline: pd.DataFrame,
        name: str,
        baseline_name: str,
    ) -> VolForecastScoreSchema:
        """Scores both on the symbol-days where both forecasts and the target exist."""
        realized = self._realized.loc[self._days]
        model = forecast.reindex_like(realized)
        base = baseline.reindex_like(realized)
        common = realized.notna() & model.notna() & base.notna()
        model_loss = self.qlike(realized, model).where(common)
        base_loss = self.qlike(realized, base).where(common)
        # One loss differential per day: the mean over that day's symbols.
        diff = (base_loss - model_loss).mean(axis=1).dropna()
        if diff.empty:
            msg = f"{name} and {baseline_name} share no scored day"
            raise ValueError(msg)
        symbols = [str(s) for s in realized.columns[common.any(axis=0)]]
        dm_stat = self.diebold_mariano(diff.to_numpy())
        return VolForecastScoreSchema(
            name=name,
            symbols=symbols,
            days=len(diff),
            mean_qlike=float(np.nanmean(model_loss.to_numpy())),
            baseline=baseline_name,
            baseline_qlike=float(np.nanmean(base_loss.to_numpy())),
            dm_stat=dm_stat,
            p_value=None
            if dm_stat is None
            else 0.5 * math.erfc(dm_stat / math.sqrt(2)),
        )

    @staticmethod
    def qlike(realized: pd.DataFrame, forecast: pd.DataFrame) -> pd.DataFrame:
        """RV/F - log(RV/F) - 1: zero for a perfect forecast, robust to noisy RV."""
        ratio = realized / forecast
        loss: pd.DataFrame = ratio - np.log(ratio) - 1
        return loss

    @staticmethod
    def diebold_mariano(diff: np.ndarray, lag: int = NEWEY_WEST_LAG) -> float | None:
        n = len(diff)
        if n <= lag:
            return None
        centered = diff - diff.mean()
        variance = float(centered @ centered) / n
        for k in range(1, lag + 1):
            weight = 1 - k / (lag + 1)
            variance += 2 * weight * float(centered[k:] @ centered[:-k]) / n
        if variance <= 0:
            return None
        return float(diff.mean() / math.sqrt(variance / n))
