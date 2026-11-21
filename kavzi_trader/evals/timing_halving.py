import logging

import numpy as np
import pandas as pd

from kavzi_trader.evals.vol_spike_halving import HOUR, PRICE

logger = logging.getLogger(__name__)


class TimingHalving:
    """Vol-spike halving on a book that is re-checked at intraday bar closes.

    The paper rule since 2026-11-21: after a day's first spike every weight the
    rule holds that day is cut to ``scale`` of itself, entries included, until
    the day's last check restores it. An intraday exit ends the halving.
    Funding is left out, as in ``VolSpikeHalving``.
    """

    def __init__(self, scale: float, fee: float) -> None:
        if not 0 <= scale <= 1:
            msg = f"scale must be in [0, 1], got {scale}"
            raise ValueError(msg)
        self._scale = scale
        self._fee = fee

    def adjustments(
        self,
        held: pd.DataFrame,
        bars: pd.DataFrame,
        hours: int,
        triggers: dict[str, pd.DataFrame],
    ) -> pd.Series:
        """Change in each return day's net return, indexed by day.

        ``held`` is weights after each check, indexed by its bar close time;
        ``bars`` holds ``hours`` bar closes indexed by open time.
        """
        closes = bars.set_axis(bars.index + pd.Timedelta(hours=hours))
        days = held.index.normalize().unique()
        total = pd.Series(0.0, index=days)
        for symbol, fired in triggers.items():
            for day, row in fired.loc[fired.index.intersection(days)].iterrows():
                total[day] += self._day(
                    held[symbol], closes[symbol], day, row[HOUR], float(row[PRICE])
                )
        logger.info(
            "Halving changed %d of %d days", int((total != 0).sum()), len(total)
        )
        return total

    def _day(
        self,
        weights: pd.Series,
        prices: pd.Series,
        day: pd.Timestamp,
        hour: pd.Timestamp,
        spike_price: float,
    ) -> float:
        spike_close = hour + pd.Timedelta(hours=1)
        end = day + pd.Timedelta(days=1)
        before = weights.loc[:spike_close]
        start_price = prices.get(day)
        # A day whose restoring check falls outside the scored window is skipped.
        if before.empty or end not in weights.index or start_price is None:
            return 0.0
        if np.isnan(start_price):
            return 0.0
        # Checks after the spike that day; the one at `end` restores the weight.
        checks = weights.loc[spike_close:end]
        checks = checks[checks.index > spike_close]
        cut = 1 - self._scale
        w = float(before.iloc[-1])
        price = spike_price
        forgone = 0.0
        # Base and halved books both start at w just before the spike.
        base_cost = 0.0
        actual_cost = abs(w - self._scale * w)
        actual = self._scale * w
        for time, weight in checks.items():
            close = float(prices[time])
            forgone += cut * w * (close - price) / start_price
            price, new = close, float(weight)
            target = new if time >= end else self._scale * new
            base_cost += abs(new - w)
            actual_cost += abs(target - actual)
            w, actual = new, target
        return -forgone - self._fee * (actual_cost - base_cost)
