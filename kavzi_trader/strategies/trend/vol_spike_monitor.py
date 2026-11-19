import logging

import numpy as np

from kavzi_trader.strategies.trend.hourly_variance_provider import (
    HourlyVarianceProvider,
)
from kavzi_trader.strategies.trend.hourly_variance_store import HourlyVarianceStore
from kavzi_trader.strategies.trend.vol_spike_config import VolSpikeConfigSchema
from kavzi_trader.strategies.trend.vol_spike_day_schema import VolSpikeDaySchema
from kavzi_trader.strategies.trend.vol_spike_reading_schema import (
    VolSpikeReadingSchema,
)

logger = logging.getLogger(__name__)

HOUR_MS = 3_600_000
DAY_MS = 86_400_000


class VolSpikeMonitor:
    """Live counterpart of evals' VolSpikeHalving.triggers, one hour at a time."""

    def __init__(
        self,
        config: VolSpikeConfigSchema,
        source: HourlyVarianceProvider,
        store: HourlyVarianceStore,
    ) -> None:
        self._config = config
        self._source = source
        self._store = store
        self._rv: dict[str, dict[int, float]] = {}
        self._price: dict[str, float] = {}

    @property
    def config(self) -> VolSpikeConfigSchema:
        return self._config

    async def day(self, symbol: str, now_ms: int) -> VolSpikeDaySchema:
        """Readings of the UTC day of ``now_ms``, over its closed hours only.

        The 23:00 hour closes on the next day, so it never halves, as in the eval.
        """
        day_start_ms = now_ms // DAY_MS * DAY_MS
        rv = await self._update(symbol, day_start_ms, now_ms // HOUR_MS * HOUR_MS)
        hours = sorted(rv)
        readings = [
            self._reading(rv, hours[:i], h)
            for i, h in enumerate(hours)
            if h >= day_start_ms
        ]
        first = next((r for r in readings if r.spike), None)
        return VolSpikeDaySchema(
            latest=readings[-1] if readings else None,
            first_spike=first,
            price=self._price.get(symbol),
        )

    def _reading(
        self, rv: dict[int, float], prior: list[int], hour_ms: int
    ) -> VolSpikeReadingSchema:
        window = [rv[h] for h in prior[-self._config.history_hours :]]
        threshold = (
            float(np.quantile(window, self._config.quantile))
            if len(window) >= self._config.min_history_hours
            else None
        )
        return VolSpikeReadingSchema(
            hour_ms=hour_ms, rv=rv[hour_ms], threshold=threshold
        )

    async def _update(
        self, symbol: str, day_start_ms: int, end_ms: int
    ) -> dict[int, float]:
        if symbol not in self._rv:
            self._rv[symbol] = await self._store.load(symbol)
        rv = self._rv[symbol]
        keep_from_ms = day_start_ms - self._config.history_hours * HOUR_MS
        stale = [h for h in rv if h < keep_from_ms]
        for hour in stale:
            del rv[hour]
        await self._store.drop(symbol, stale)

        start_ms = max(keep_from_ms, max(rv, default=0) + HOUR_MS)
        if start_ms >= end_ms:
            return rv
        if (end_ms - start_ms) // HOUR_MS > 1:
            logger.info(
                "Backfilling %d hours of 1m variance for %s",
                (end_ms - start_ms) // HOUR_MS,
                symbol,
            )
        fetched = await self._source.hours(symbol, start_ms, end_ms)
        new = {h.hour_ms: h.rv for h in fetched}
        rv.update(new)
        await self._store.save(symbol, new)
        if fetched:
            self._price[symbol] = fetched[-1].close
        return rv
