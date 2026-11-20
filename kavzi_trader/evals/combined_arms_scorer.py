import logging

import pandas as pd

from kavzi_trader.evals.combined_arms_result_schema import CombinedArmsResultSchema
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.evals.validation.paired_sharpe_test import PairedSharpeTest
from kavzi_trader.evals.vol_spike_halving import VolSpikeHalving
from kavzi_trader.evals.weight_backtest import WeightBacktest
from kavzi_trader.evals.weight_signal import WeightSignal
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)


class CombinedArmsScorer:
    """Scores exit rule x vol-spike halving as a 2x2 on one set of daily bars.

    Halving is applied to each exit rule's own held weights, so its cost or
    benefit is measured against the book that exit rule actually holds.
    """

    def __init__(
        self,
        base_signal: WeightSignal,
        mid_signal: WeightSignal,
        halving: VolSpikeHalving,
        band: float,
        fee: float,
        metrics: TrendMetrics,
    ) -> None:
        self._signals = {"base": base_signal, "mid": mid_signal}
        self._halving = halving
        self._band = band
        self._fee = fee
        self._metrics = metrics

    def run(
        self,
        data: TrendDataSchema,
        triggers: dict[str, pd.DataFrame],
        first_day: pd.Timestamp,
        last_day: pd.Timestamp,
    ) -> CombinedArmsResultSchema:
        plain: dict[str, TrendResultSchema] = {}
        halved: dict[str, TrendResultSchema] = {}
        spikes: dict[str, int] = {}
        for name, signal in self._signals.items():
            backtest = WeightBacktest(
                signal,
                TurnoverBuffer(self._band),
                TrendPortfolio(self._fee),
                self._metrics,
            )
            plain[name] = backtest.run(data, first_day, last_day)
            held = backtest.held_weights(data, first_day, last_day)
            change = self._halving.adjustments(held, data.closes, triggers, self._fee)
            halved[name] = self._with_halving(plain[name], held.index, change)
            spikes[name] = self._spike_days(held, triggers)
            logger.info("Arm %s: %d held spike days", name, spikes[name])
        test = PairedSharpeTest()
        net = {
            "base": plain["base"].daily_net,
            "mid": plain["mid"].daily_net,
            "halving": halved["base"].daily_net,
            "mid_halving": halved["mid"].daily_net,
        }
        return CombinedArmsResultSchema(
            base=plain["base"],
            mid=plain["mid"],
            halving=halved["base"],
            mid_halving=halved["mid"],
            spike_days_base=spikes["base"],
            spike_days_mid=spikes["mid"],
            mid_gain_with_halving=test.compare(net["halving"], net["mid_halving"]),
            mid_gain_alone=test.compare(net["base"], net["mid"]),
            halving_change_under_mid=test.compare(net["mid"], net["mid_halving"]),
            halving_change_under_base=test.compare(net["base"], net["halving"]),
            combined_vs_base=test.compare(net["base"], net["mid_halving"]),
        )

    def _with_halving(
        self, result: TrendResultSchema, days: pd.DatetimeIndex, change: pd.Series
    ) -> TrendResultSchema:
        net = pd.Series(result.daily_net, index=days) + change
        return result.model_copy(
            update={"net": self._metrics.stats(net), "daily_net": net.tolist()}
        )

    @staticmethod
    def _spike_days(held: pd.DataFrame, triggers: dict[str, pd.DataFrame]) -> int:
        count = 0
        for symbol, fired in triggers.items():
            days = held.index.intersection(fired.index)
            count += int((held.loc[days, symbol] != 0).sum())
        return count
