import logging

import numpy as np
import pandas as pd

from kavzi_trader.evals.funding_xs_day_schema import FundingXsDaySchema
from kavzi_trader.evals.funding_xs_leg_picker import FundingXsLegPicker
from kavzi_trader.evals.funding_xs_params_schema import FundingXsParamsSchema
from kavzi_trader.evals.funding_xs_run_schema import FundingXsRunSchema
from kavzi_trader.evals.series_cache import TIME, VALUE

logger = logging.getLogger(__name__)


class FundingXsBacktester:
    """Market-neutral funding rank: short the highest scores, long the lowest.

    ``prices`` has one row per daily mark; row 0 is the first rebalance. Notional
    is fixed at each rebalance, so a hold's P&L is the sum of leg moves on it.
    """

    def __init__(
        self,
        prices: pd.DataFrame,
        settlements: dict[str, pd.DataFrame],
        params: FundingXsParamsSchema,
    ) -> None:
        self._prices = prices
        self._params = params
        self._marks = prices.index.to_numpy(dtype=np.int64)
        self._times = {s: f[TIME].to_numpy(dtype=np.int64) for s, f in settlements.items()}
        self._values = {s: f[VALUE].to_numpy(dtype=np.float64) for s, f in settlements.items()}
        self._cum = {
            s: np.concatenate(([0.0], np.cumsum(v))) for s, v in self._values.items()
        }
        self._picker = FundingXsLegPicker(params.legs)

    def scores(self, at_ms: int) -> dict[str, float]:
        """Mean of each symbol's last settlements strictly before ``at_ms``."""
        n = self._params.score_settlements
        result = {}
        for symbol, times in self._times.items():
            end = int(np.searchsorted(times, at_ms, side="left"))
            if end >= n:
                result[symbol] = float(self._values[symbol][end - n : end].mean())
        return result

    def funding_rate_sum(self, symbol: str, from_ms: int, to_ms: int) -> float:
        """Sum of settled rates in [from_ms, to_ms)."""
        times = self._times[symbol]
        lo = int(np.searchsorted(times, from_ms, side="left"))
        hi = int(np.searchsorted(times, to_ms, side="left"))
        return float(self._cum[symbol][hi] - self._cum[symbol][lo])

    def run(self) -> FundingXsRunSchema:
        last = len(self._marks) - 1
        equity = 1.0
        weights: dict[str, float] = {}
        days: list[FundingXsDaySchema] = []
        rebalances = skipped = 0
        turnover = 0.0
        start = 0
        while start < last:
            end = min(start + self._params.hold_days, last)
            target = self._target_weights(start)
            if not target:
                skipped += 1
                logger.warning("Too few scored symbols at mark %d", self._marks[start])
            rebalances += 1
            change = _abs_change(weights, target)
            turnover += change
            cost = self._params.cost_rate * change * equity
            hold = self._hold_days(start, end, target, equity, cost)
            days.extend(hold)
            equity = hold[-1].equity
            weights = target
            start = end
        return FundingXsRunSchema(
            days=days, rebalances=rebalances, skipped_rebalances=skipped, turnover=turnover
        )

    def _target_weights(self, row: int) -> dict[str, float]:
        scores = self.scores(int(self._marks[row]))
        priced = self._prices.iloc[row]
        scores = {s: v for s, v in scores.items() if not np.isnan(priced[s])}
        if len(scores) < 2 * self._params.legs:
            return {}
        legs = self._picker.pick(scores)
        w = self._params.leg_weight
        return {**{s: w for s in legs.longs}, **{s: -w for s in legs.shorts}}

    def _hold_days(
        self,
        start: int,
        end: int,
        weights: dict[str, float],
        equity: float,
        cost: float,
    ) -> list[FundingXsDaySchema]:
        entry = self._prices.iloc[start]
        days = []
        prev_price = prev_funding = 0.0
        prev_equity = equity
        for row in range(start + 1, end + 1):
            now = self._prices.iloc[row]
            price = _price_pnl(weights, entry, now)
            # A long pays positive funding, a short receives it.
            funding = -sum(
                w * self.funding_rate_sum(s, int(self._marks[start]), int(self._marks[row]))
                for s, w in weights.items()
            )
            day_cost = cost if row == start + 1 else 0.0
            d_price = equity * (price - prev_price)
            d_funding = equity * (funding - prev_funding)
            new_equity = prev_equity + d_price + d_funding - day_cost
            days.append(
                FundingXsDaySchema(
                    day_ms=int(self._marks[row - 1]),
                    price_return=d_price / prev_equity,
                    funding_return=d_funding / prev_equity,
                    cost_return=-day_cost / prev_equity,
                    equity=new_equity,
                )
            )
            prev_price, prev_funding, prev_equity = price, funding, new_equity
        return days


def _price_pnl(
    weights: dict[str, float], entry: pd.Series, now: pd.Series
) -> float:
    total = 0.0
    for symbol, w in weights.items():
        if np.isnan(now[symbol]):
            msg = f"no price for held {symbol} at a daily mark"
            raise ValueError(msg)
        total += w * (now[symbol] / entry[symbol] - 1.0)
    return total


def _abs_change(old: dict[str, float], new: dict[str, float]) -> float:
    symbols = old.keys() | new.keys()
    return sum(abs(new.get(s, 0.0) - old.get(s, 0.0)) for s in symbols)
