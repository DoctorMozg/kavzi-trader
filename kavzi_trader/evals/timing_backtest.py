import logging

import numpy as np
import pandas as pd

from kavzi_trader.evals.intraday_data_schema import IntradayDataSchema
from kavzi_trader.evals.timing_arm_schema import TimingArmSchema
from kavzi_trader.evals.timing_inputs_schema import TimingInputsSchema
from kavzi_trader.evals.timing_result_schema import TimingResultSchema
from kavzi_trader.evals.timing_states import TimingStates
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.strategies.trend.donchian_trend_signal import DAYS_PER_YEAR
from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)


class TimingBacktest:
    """Scores the mid-exit trend rule checked at bar closes instead of daily.

    The book holds weights set at one bar close until the next. Sizing is the
    base's: vol from daily log returns known then (the last completed day), the
    same target, cap, 1/N and buffer. A weight is notional per unit of the
    day-start price, so a day without weight changes earns exactly the base's
    day return however many bars it has, and 24h bars reproduce the base.
    Commission is charged on each weight change in the interval that follows it;
    a day's funding is paid on the time-weighted held weight.
    """

    def __init__(
        self,
        params: TrendParamsSchema,
        buffer: TurnoverBuffer,
        portfolio: TrendPortfolio,
        metrics: TrendMetrics,
    ) -> None:
        if len(params.lookbacks) != 1:
            msg = f"timing arms use one lookback, got {params.lookbacks}"
            raise ValueError(msg)
        self._signal = MidExitTrendSignal(params)
        self._states = TimingStates(self._signal, params.lookbacks[0])
        self._buffer = buffer
        self._portfolio = portfolio
        self._metrics = metrics

    def run(
        self,
        arm: TimingArmSchema,
        data: TrendDataSchema,
        intraday: IntradayDataSchema,
        first_day: pd.Timestamp,
        last_day: pd.Timestamp,
    ) -> TimingResultSchema:
        """Scores return days from ``first_day`` to ``last_day``, both inclusive."""
        inputs = self._scored(arm, data, intraday, first_day, last_day)
        run = self._portfolio.run(inputs.held, inputs.returns, inputs.funding)
        rows = pd.DataFrame(
            {
                "net": run.net,
                "traded": run.traded,
                "cost": run.cost,
                "fund": run.funding,
            }
        )
        daily = rows.groupby(inputs.days.to_numpy()).sum()
        net = daily["net"]
        logger.info(
            "Arm %s: %d symbols, %d days", arm.label, data.closes.shape[1], len(net)
        )
        return TimingResultSchema(
            result=TrendResultSchema(
                symbols=list(data.closes.columns),
                first_day=net.index[0].date().isoformat(),
                last_day=net.index[-1].date().isoformat(),
                days=len(net),
                net=self._metrics.stats(net),
                benchmark=self._metrics.stats(self._benchmark(data, net.index)),
                turnover_per_year=float(daily["traded"].mean() * DAYS_PER_YEAR),
                cost_drag=float(daily["cost"].mean() * DAYS_PER_YEAR),
                funding_drag=float(daily["fund"].mean() * DAYS_PER_YEAR),
                cash_return=self._metrics.cash_return(net.index),
                daily_net=net.tolist(),
            ),
            trades_per_year=self.trades_per_year(inputs.held, len(net)),
        )

    def held_weights(
        self,
        arm: TimingArmSchema,
        data: TrendDataSchema,
        intraday: IntradayDataSchema,
        first_day: pd.Timestamp,
        last_day: pd.Timestamp,
    ) -> pd.DataFrame:
        """Weights held after each scored bar close, indexed by that close."""
        inputs = self._scored(arm, data, intraday, first_day, last_day)
        return pd.DataFrame(
            inputs.held, index=inputs.checkpoints, columns=data.closes.columns
        )

    @staticmethod
    def trades_per_year(held: np.ndarray, n_days: int) -> float:
        """Weight changes over symbols and checks, from a flat start, per year."""
        previous = np.vstack([np.zeros(held.shape[1]), held[:-1]])
        return float((held != previous).sum() / (n_days / DAYS_PER_YEAR))

    def _scored(
        self,
        arm: TimingArmSchema,
        data: TrendDataSchema,
        intraday: IntradayDataSchema,
        first_day: pd.Timestamp,
        last_day: pd.Timestamp,
    ) -> TimingInputsSchema:
        closes = data.closes
        per_day = arm.bars_per_day
        prices = intraday.bars.to_numpy(dtype=float)
        if intraday.hours != arm.hours or prices.shape != (
            len(closes) * per_day,
            closes.shape[1],
        ):
            msg = (
                f"{intraday.hours}h bars of shape {prices.shape} do not fit arm "
                f"{arm.label} over closes {closes.shape}"
            )
            raise ValueError(msg)
        daily = closes.to_numpy(dtype=float)
        if arm.approach == "A":
            states = self._states.on_bars(prices)
        else:
            states = self._states.on_daily_channel(daily, prices, per_day)
        targets = states * self._bar_scale(daily, per_day) / closes.shape[1]
        targets = np.where(np.repeat(~np.isnan(daily), per_day, axis=0), targets, 0.0)

        # Row r holds the weights set at bar r from its close to the next bar's.
        rows = np.arange(len(prices) - 1)
        day_of_row = (rows + 1) // per_day
        return_day = closes.index[day_of_row]
        scored = (
            (day_of_row >= 1) & (return_day >= first_day) & (return_day <= last_day)
        )
        if not scored.any():
            msg = f"no return days between {first_day.date()} and {last_day.date()}"
            raise ValueError(msg)
        rows, day_of_row = rows[scored], day_of_row[scored]
        day_start = prices[day_of_row * per_day - 1]
        with np.errstate(invalid="ignore"):
            returns = (prices[rows + 1] - prices[rows]) / day_start
        untraded = (
            np.isnan(returns)
            | np.isnan(daily[day_of_row])
            | np.isnan(daily[day_of_row - 1])
        )
        funding = data.funding.to_numpy(dtype=float)[day_of_row] / per_day
        return TimingInputsSchema(
            checkpoints=intraday.bars.index[rows] + pd.Timedelta(hours=arm.hours),
            days=pd.DatetimeIndex(return_day[scored]),
            held=self._buffer.apply(targets[rows]),
            returns=np.where(untraded, 0.0, returns),
            funding=np.where(untraded, 0.0, funding),
        )

    def _bar_scale(self, daily: np.ndarray, per_day: int) -> np.ndarray:
        """Vol scale per bar: the day's own at its close, else the previous day's."""
        scale = np.column_stack(
            [self._signal.vol_scale(daily[:, j]) for j in range(daily.shape[1])]
        )
        previous = np.vstack([np.zeros((1, scale.shape[1])), scale[:-1]])
        per_bar = np.repeat(previous, per_day, axis=0)
        per_bar[per_day - 1 :: per_day] = scale
        return per_bar

    @staticmethod
    def _benchmark(data: TrendDataSchema, days: pd.DatetimeIndex) -> pd.Series:
        """Equal weight over the symbols listed that day, as the base's benchmark."""
        raw = data.closes.pct_change()
        return pd.Series(np.nanmean(raw.loc[days].to_numpy(), axis=1), index=days)
