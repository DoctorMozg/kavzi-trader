import logging

import numpy as np
import pandas as pd
import torch
from chronos import BaseChronosPipeline  # type: ignore[import-untyped]

from kavzi_trader.evals.realized_variance import HORIZON_DAYS, RealizedVariance

logger = logging.getLogger(__name__)

CHRONOS_MODEL = "amazon/chronos-2"
_MIN_CONTEXT_DAYS = 64
_MEDIAN = 0.5


class ChronosVolForecaster:
    """Zero-shot Chronos-2 forecast of each symbol's log 7-day variance series.

    The context at close t is the trailing log RV7 series up to t; the median of
    step 7 is the log variance of days t+1 .. t+7. No fitting on our data.
    """

    def __init__(
        self,
        first_forecast_day: pd.Timestamp,
        revision: str,
        context_days: int = 512,
        batch_size: int = 256,
    ) -> None:
        self._first = first_forecast_day
        self._revision = revision
        self._context = context_days
        self._batch = batch_size

    @property
    def name(self) -> str:
        return "chronos-2"

    def forecast(self, returns: pd.DataFrame) -> pd.DataFrame:
        torch.manual_seed(0)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        pipeline = BaseChronosPipeline.from_pretrained(
            CHRONOS_MODEL, revision=self._revision, device_map=device
        )
        log_rv = np.log(RealizedVariance.backward(returns, HORIZON_DAYS))
        out = pd.DataFrame(np.nan, index=returns.index, columns=returns.columns)
        for symbol in returns.columns:
            positions, contexts = self._contexts(log_rv[symbol])
            if not contexts:
                continue
            quantiles, _ = pipeline.predict_quantiles(
                contexts,
                prediction_length=HORIZON_DAYS,
                quantile_levels=[_MEDIAN],
                batch_size=self._batch,
            )
            medians = np.array([q[0, -1, 0].item() for q in quantiles])
            out.iloc[positions, out.columns.get_loc(symbol)] = np.exp(medians)
            logger.info(
                "chronos-2: %s %d forecasts on %s", symbol, len(contexts), device
            )
        return out

    def _contexts(self, series: pd.Series) -> tuple[list[int], list[torch.Tensor]]:
        values = series.to_numpy()
        positions: list[int] = []
        contexts: list[torch.Tensor] = []
        for t in np.flatnonzero(series.index >= self._first):
            history = values[: t + 1]
            history = history[np.isfinite(history)][-self._context :]
            if len(history) >= _MIN_CONTEXT_DAYS and np.isfinite(values[t]):
                positions.append(int(t))
                contexts.append(torch.tensor(history, dtype=torch.float32))
        return positions, contexts
