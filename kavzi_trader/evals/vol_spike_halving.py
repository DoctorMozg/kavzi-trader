import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

HOUR_MS = 3_600_000
HOUR = "hour"
PRICE = "price"
_HOURS_PER_DAY = 24


class VolSpikeHalving:
    """Halve a coin's position for the rest of the day after a 1-hour vol spike.

    A spike: the hour's realized variance of 1m log returns exceeds the 99th
    percentile of the previous ``history_hours`` hours. The position halves at
    that hour's last close and is restored at the next daily rebalance. The last
    hour of the day never triggers: the rebalance follows it.
    """

    def __init__(
        self,
        history_hours: int = 2160,
        min_history_hours: int = 720,
        quantile: float = 0.99,
        scale: float = 0.5,
    ) -> None:
        self._history = history_hours
        self._min_history = min_history_hours
        self._quantile = quantile
        self._scale = scale

    @property
    def scale(self) -> float:
        return self._scale

    def triggers(self, minutes: pd.DataFrame) -> pd.DataFrame:
        """First spike hour of each UTC day: ``HOUR`` start time and its last ``PRICE``.

        ``minutes`` has ``open_time_ms`` and ``close`` of 1m bars.
        """
        frame = minutes.sort_values("open_time_ms")
        log_ret = np.log(frame["close"]).diff()
        hour_ms = frame["open_time_ms"] // HOUR_MS * HOUR_MS
        hourly = pd.DataFrame(
            {
                "rv": log_ret.pow(2).groupby(hour_ms).sum(),
                PRICE: frame["close"].groupby(hour_ms).last(),
            }
        )
        threshold = (
            hourly["rv"]
            .rolling(self._history, min_periods=self._min_history)
            .quantile(self._quantile)
            .shift(1)
        )
        start = pd.to_datetime(hourly.index, unit="ms")
        spike = (hourly["rv"] > threshold).to_numpy() & (
            start.hour < _HOURS_PER_DAY - 1
        )
        fired = pd.DataFrame(
            {HOUR: start[spike], PRICE: hourly[PRICE].to_numpy()[spike]},
            index=start[spike].normalize(),
        )
        first = fired[~fired.index.duplicated()]
        logger.info(
            "Vol spikes on %d of %d days", len(first), start.normalize().nunique()
        )
        return first

    def adjustments(
        self,
        held: pd.DataFrame,
        closes: pd.DataFrame,
        triggers: dict[str, pd.DataFrame],
        fee: float,
    ) -> pd.Series:
        """Change in each return day's net return if every spike had halved the coin.

        Selling half at the spike price forgoes half the move to the close; the
        half sold and bought back at the rebalance costs ``fee`` per unit each way.
        """
        total = pd.Series(0.0, index=held.index)
        for symbol, fired in triggers.items():
            days = held.index.intersection(fired.index)
            weight = held.loc[days, symbol]
            prev_close = closes[symbol].shift(1).reindex(days)
            close = closes[symbol].reindex(days)
            forgone = (
                (1 - self._scale)
                * weight
                * (close - fired.loc[days, PRICE])
                / prev_close
            )
            traded = 2 * (1 - self._scale) * weight.abs() * fee
            change = (-forgone - traded).where(weight != 0, 0.0).fillna(0.0)
            total = total.add(change, fill_value=0.0)
        return total
