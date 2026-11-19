import logging
from datetime import date, timedelta

import pandas as pd

from kavzi_trader.evals.date_window_schema import DateWindowSchema
from kavzi_trader.evals.scheduled_signal import ScheduledSignal
from kavzi_trader.evals.signal_period_schema import SignalPeriodSchema
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.walk_forward_choice_schema import WalkForwardChoiceSchema
from kavzi_trader.evals.walk_forward_result_schema import WalkForwardResultSchema
from kavzi_trader.evals.weight_backtest import WeightBacktest
from kavzi_trader.evals.weight_signal import WeightSignal
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)


class WalkForward:
    """Picks a lookback per calendar year from the years before it, then scores them."""

    def __init__(
        self,
        candidates: dict[int, WeightSignal],
        buffer: TurnoverBuffer,
        portfolio: TrendPortfolio,
        metrics: TrendMetrics,
    ) -> None:
        if not candidates:
            msg = "need at least one candidate lookback"
            raise ValueError(msg)
        self._candidates = candidates
        self._buffer = buffer
        self._portfolio = portfolio
        self._metrics = metrics

    @staticmethod
    def calendar_years(span: DateWindowSchema) -> list[DateWindowSchema]:
        """Test periods: each calendar year of ``span``, cut at its ends."""
        periods = []
        start = span.first_day
        while start <= span.last_day:
            end = min(date(start.year, 12, 31), span.last_day)
            periods.append(DateWindowSchema(first_day=start, last_day=end))
            start = end + timedelta(days=1)
        return periods

    def run(
        self,
        data: TrendDataSchema,
        train_first_day: date,
        periods: list[DateWindowSchema],
    ) -> WalkForwardResultSchema:
        if not periods or periods[0].first_day <= train_first_day:
            msg = f"test periods must start after training starts on {train_first_day}"
            raise ValueError(msg)
        choices = [self._choose(data, train_first_day, period) for period in periods]
        scheduled = ScheduledSignal(
            [
                SignalPeriodSchema(
                    first_day=c.window.first_day,
                    last_day=c.window.last_day,
                    signal=self._candidates[c.lookback],
                )
                for c in choices
            ]
        )
        out_of_sample = self._backtest(scheduled).run(
            data,
            pd.Timestamp(periods[0].first_day),
            pd.Timestamp(periods[-1].last_day),
        )
        return WalkForwardResultSchema(
            train_first_day=train_first_day,
            choices=choices,
            out_of_sample=out_of_sample,
        )

    def _choose(
        self, data: TrendDataSchema, train_first: date, period: DateWindowSchema
    ) -> WalkForwardChoiceSchema:
        train_last = pd.Timestamp(period.first_day - timedelta(days=1))
        scores = {
            lookback: self._backtest(signal)
            .run(data, pd.Timestamp(train_first), train_last)
            .net.sharpe
            for lookback, signal in self._candidates.items()
        }
        # Highest training Sharpe wins; a tie goes to the shorter lookback.
        lookback = max(
            scores, key=lambda lb: (scores[lb] is not None, scores[lb] or 0.0, -lb)
        )
        logger.info(
            "Walk-forward %s..%s: lookback %d (train Sharpe %s)",
            period.first_day,
            period.last_day,
            lookback,
            scores[lookback],
        )
        return WalkForwardChoiceSchema(window=period, lookback=lookback, scores=scores)

    def _backtest(self, signal: WeightSignal) -> WeightBacktest:
        return WeightBacktest(signal, self._buffer, self._portfolio, self._metrics)
