import logging

import numpy as np
import pandas as pd

from kavzi_trader.evals.donchian_trend_signal import (
    DAYS_PER_YEAR,
    DonchianTrendSignal,
)
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.evals.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)

# Return days scored by the preregistration; earlier days only warm up lookbacks.
FIRST_RETURN_DAY = pd.Timestamp("2022-03-15")
LAST_RETURN_DAY = pd.Timestamp("2026-11-14")


class TrendBacktest:
    """Wires signal, turnover buffer and portfolio accounting over daily data."""

    def __init__(
        self,
        signal: DonchianTrendSignal,
        buffer: TurnoverBuffer,
        portfolio: TrendPortfolio,
    ) -> None:
        self._signal = signal
        self._buffer = buffer
        self._portfolio = portfolio

    def run(self, data: TrendDataSchema) -> TrendResultSchema:
        closes = data.closes
        n_symbols = closes.shape[1]
        weights = np.column_stack(
            [
                self._signal.compute(closes[s].to_numpy(), n_symbols).weight
                for s in closes
            ]
        )
        # Weights set at close of day d earn day d+1's close-to-close return.
        returns = closes.pct_change().shift(-1).to_numpy()
        funding = data.funding.shift(-1).to_numpy()
        return_day = closes.index.to_series().shift(-1)
        scored = (
            (return_day >= FIRST_RETURN_DAY) & (return_day <= LAST_RETURN_DAY)
        ).to_numpy()
        if not scored.any():
            msg = "no return days inside the preregistered window"
            raise ValueError(msg)

        held = self._buffer.apply(weights[scored])
        run = self._portfolio.run(held, returns[scored], funding[scored])
        days = pd.DatetimeIndex(return_day[scored])
        logger.info("Backtest %d symbols over %d days", n_symbols, len(days))

        metrics = TrendMetrics()
        benchmark = pd.Series(returns[scored].mean(axis=1), index=days)
        return TrendResultSchema(
            symbols=list(closes.columns),
            first_day=days[0].date().isoformat(),
            last_day=days[-1].date().isoformat(),
            days=len(days),
            net=metrics.stats(pd.Series(run.net, index=days)),
            benchmark=metrics.stats(benchmark),
            turnover_per_year=float(run.traded.mean() * DAYS_PER_YEAR),
            cost_drag=float(run.cost.mean() * DAYS_PER_YEAR),
            funding_drag=float(run.funding.mean() * DAYS_PER_YEAR),
        )
