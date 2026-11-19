from typing import cast

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.evals.vol_spike_halving import HOUR, VolSpikeHalving
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.strategies.trend.hourly_variance_store import HourlyVarianceStore
from kavzi_trader.strategies.trend.minute_variance_source import MinuteVarianceSource
from kavzi_trader.strategies.trend.vol_spike_config import VolSpikeConfigSchema
from kavzi_trader.strategies.trend.vol_spike_monitor import (
    DAY_MS,
    HOUR_MS,
    VolSpikeMonitor,
)
from tests.strategies.trend.fake_minute_exchange import MINUTE_MS, FakeMinuteExchange

START_MS = 20_000 * DAY_MS
DAYS = 6
CONFIG = VolSpikeConfigSchema(history_hours=48, min_history_hours=24)
# Hours from START_MS and how much more volatile their 1m returns are; 143 is
# 23:00 on the last day.
SPIKE_HOURS = {60: 6, 75: 6, 100: 6, 143: 20}


@pytest.fixture
def minutes() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    count = DAYS * 24 * 60
    returns = rng.normal(0.0, 0.001, count)
    for hour, scale in SPIKE_HOURS.items():
        returns[hour * 60 : (hour + 1) * 60] *= scale
    return pd.DataFrame(
        {
            "open_time_ms": START_MS + np.arange(count) * MINUTE_MS,
            "close": 100 * np.exp(returns.cumsum()),
        }
    )


@pytest.fixture
def exchange(minutes: pd.DataFrame) -> FakeMinuteExchange:
    return FakeMinuteExchange(minutes)


@pytest.fixture
def store() -> HourlyVarianceStore:
    return HourlyVarianceStore(RedisStateClient.in_memory())


def monitor_for(
    exchange: FakeMinuteExchange, store: HourlyVarianceStore
) -> VolSpikeMonitor:
    source = MinuteVarianceSource(cast("ExchangeClient", exchange), page_pause_s=0)
    return VolSpikeMonitor(CONFIG, source, store)


def last_check_ms(day: int) -> int:
    """Just after hour 22 of ``day`` closes, the last hour that can halve."""
    return START_MS + day * DAY_MS + 23 * HOUR_MS + MINUTE_MS


class TestVolSpikeMonitor:
    async def test_fires_on_the_same_hours_as_the_eval_rule(
        self,
        minutes: pd.DataFrame,
        exchange: FakeMinuteExchange,
        store: HourlyVarianceStore,
    ) -> None:
        eval_rule = VolSpikeHalving(
            history_hours=CONFIG.history_hours,
            min_history_hours=CONFIG.min_history_hours,
        )
        expected = {
            int(day.value // 1_000_000): int(hour.value // 1_000_000)
            for day, hour in eval_rule.triggers(minutes)[HOUR].items()
        }
        monitor = monitor_for(exchange, store)

        fired = {}
        for day in range(DAYS):
            spike = (await monitor.day("BTCUSDT", last_check_ms(day))).first_spike
            if spike is not None:
                fired[START_MS + day * DAY_MS] = spike.hour_ms

        assert fired == expected
        assert {START_MS + d * DAY_MS for d in (2, 3, 4)} <= set(fired)

    async def test_no_threshold_before_min_history(
        self, exchange: FakeMinuteExchange, store: HourlyVarianceStore
    ) -> None:
        day = await monitor_for(exchange, store).day("BTCUSDT", last_check_ms(0))

        assert day.latest is not None
        assert day.latest.threshold is None
        assert day.first_spike is None

    async def test_restart_reads_history_from_the_store(
        self, exchange: FakeMinuteExchange, store: HourlyVarianceStore
    ) -> None:
        first = await monitor_for(exchange, store).day("BTCUSDT", last_check_ms(3))
        exchange.requests.clear()

        again = await monitor_for(exchange, store).day("BTCUSDT", last_check_ms(3))

        assert again.latest == first.latest
        assert again.first_spike == first.first_spike
        assert exchange.requests == []

    async def test_next_hour_fetches_only_that_hour(
        self, exchange: FakeMinuteExchange, store: HourlyVarianceStore
    ) -> None:
        monitor = monitor_for(exchange, store)
        await monitor.day("BTCUSDT", last_check_ms(3) - HOUR_MS)
        exchange.requests.clear()

        day = await monitor.day("BTCUSDT", last_check_ms(3))

        hour_ms = START_MS + 3 * DAY_MS + 22 * HOUR_MS
        assert exchange.requests == [(hour_ms - MINUTE_MS, hour_ms + HOUR_MS - 1)]
        assert day.latest is not None
        assert day.latest.hour_ms == hour_ms

    async def test_hour_23_never_halves(
        self, exchange: FakeMinuteExchange, store: HourlyVarianceStore
    ) -> None:
        hour_23_ms = START_MS + 143 * HOUR_MS
        monitor = monitor_for(exchange, store)
        late = await monitor.day("BTCUSDT", hour_23_ms + HOUR_MS - 1)
        next_day = await monitor.day("BTCUSDT", hour_23_ms + HOUR_MS)

        assert late.latest is not None
        assert late.latest.hour_ms == hour_23_ms - HOUR_MS
        assert next_day.latest is None
        assert next_day.first_spike is None
