import logging

import pandas as pd

from kavzi_trader.evals.intraday_data_schema import IntradayDataSchema
from kavzi_trader.evals.timing_arm_outcome_schema import TimingArmOutcomeSchema
from kavzi_trader.evals.timing_arm_schema import TIMING_ARMS, TimingArmSchema
from kavzi_trader.evals.timing_backtest import TimingBacktest
from kavzi_trader.evals.timing_result_schema import TimingResultSchema
from kavzi_trader.evals.timing_run_schema import TimingRunSchema
from kavzi_trader.evals.timing_verdict import TimingVerdict
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.validation.paired_sharpe_test import PairedSharpeTest
from kavzi_trader.evals.weight_backtest import WeightBacktest
from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)


class TimingScorer:
    """Scores timing arms against the daily paper rule on one universe."""

    def __init__(
        self,
        params: TrendParamsSchema,
        band: float,
        fee: float,
        metrics: TrendMetrics,
        verdict: TimingVerdict,
    ) -> None:
        self._params = params
        self._band = band
        self._fee = fee
        self._metrics = metrics
        self._verdict = verdict

    def run(
        self,
        universe: str,
        data: TrendDataSchema,
        intraday: dict[int, IntradayDataSchema],
        first_day: pd.Timestamp,
        last_day: pd.Timestamp,
        arms: tuple[TimingArmSchema, ...] = TIMING_ARMS,
    ) -> TimingRunSchema:
        base = self._base(data, first_day, last_day)
        backtest = TimingBacktest(
            self._params,
            TurnoverBuffer(self._band),
            TrendPortfolio(self._fee),
            self._metrics,
        )
        plain = PairedSharpeTest()
        adjusted = PairedSharpeTest(confidence=self._verdict.adjusted_confidence)
        outcomes = []
        for arm in arms:
            scored = backtest.run(arm, data, intraday[arm.hours], first_day, last_day)
            outcomes.append(
                TimingArmOutcomeSchema(
                    arm=arm,
                    scored=scored,
                    paired=plain.compare(
                        base.result.daily_net, scored.result.daily_net
                    ),
                    adjusted=adjusted.compare(
                        base.result.daily_net, scored.result.daily_net
                    ),
                )
            )
        quality = [intraday[h].quality for h in sorted(intraday, reverse=True)]
        return TimingRunSchema(
            universe=universe,
            base=base,
            arms=outcomes,
            quality=quality,
            reproduction_error=self._verdict.reproduction_error(
                universe, base.result.net.sharpe
            ),
            quality_error=self._verdict.quality_error(quality),
        )

    def _base(
        self, data: TrendDataSchema, first_day: pd.Timestamp, last_day: pd.Timestamp
    ) -> TimingResultSchema:
        """The paper rule through the same daily path the 2026-11-19 trials used."""
        backtest = WeightBacktest(
            MidExitTrendSignal(self._params),
            TurnoverBuffer(self._band),
            TrendPortfolio(self._fee),
            self._metrics,
        )
        result = backtest.run(data, first_day, last_day)
        held = backtest.held_weights(data, first_day, last_day).to_numpy()
        return TimingResultSchema(
            result=result,
            trades_per_year=TimingBacktest.trades_per_year(held, result.days),
        )
