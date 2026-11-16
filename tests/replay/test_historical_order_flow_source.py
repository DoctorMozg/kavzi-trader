from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.commons.sim_clock import SimClock
from kavzi_trader.evals.metrics_cache import GLOBAL_RATIO
from kavzi_trader.evals.series_cache import TIME, VALUE
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.orchestrator.providers.live_order_flow_fetcher import (
    LiveOrderFlowFetcher,
)
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.order_flow.calculator import OrderFlowCalculator
from kavzi_trader.replay.historical_order_flow_source import (
    HistoricalOrderFlowSource,
)

SYMBOL = "BTCUSDT"
T0_MS = 1_609_459_200_000
HOUR_MS = 3_600_000
FIVE_MIN_MS = 300_000


@pytest.fixture
def clock() -> SimClock:
    return SimClock(T0_MS + 30 * HOUR_MS)


@pytest.fixture
def source(clock: SimClock) -> HistoricalOrderFlowSource:
    settle = T0_MS + np.arange(6) * 8 * HOUR_MS
    snaps = T0_MS + np.arange(48 * 12) * FIVE_MIN_MS
    oi = 1000.0 + np.arange(len(snaps))
    return HistoricalOrderFlowSource(
        clock,
        funding={
            SYMBOL: pd.DataFrame({TIME: settle, VALUE: 0.0001 * (1 + np.arange(6))})
        },
        open_interest={SYMBOL: pd.DataFrame({TIME: snaps, VALUE: oi})},
        metrics={SYMBOL: pd.DataFrame({TIME: snaps, GLOBAL_RATIO: 3.0})},
    )


class TestRowsKnownAtTheClock:
    async def test_funding_stops_at_the_last_settlement_before_now(
        self, source: HistoricalOrderFlowSource
    ) -> None:
        rows = await source.get_funding_rate(SYMBOL, limit=100)

        # Settlements at 0h, 8h, 16h and 24h precede 30h; 32h does not.
        assert [r["fundingTime"] for r in rows] == [
            T0_MS + h * HOUR_MS for h in (0, 8, 16, 24)
        ]

    async def test_open_interest_keeps_period_aligned_rows(
        self, source: HistoricalOrderFlowSource
    ) -> None:
        rows = await source.get_open_interest_history(SYMBOL, period="15m", limit=3)

        assert [r["timestamp"] for r in rows] == [
            T0_MS + 30 * HOUR_MS - k * 900_000 for k in (2, 1, 0)
        ]

    async def test_long_short_ratio_splits_accounts(
        self, source: HistoricalOrderFlowSource
    ) -> None:
        [row] = await source.get_long_short_ratio(SYMBOL, period="15m", limit=1)

        assert Decimal(row["longAccount"]) == Decimal("0.75")
        assert Decimal(row["shortAccount"]) == Decimal("0.25")

    async def test_unknown_symbol_has_no_rows(
        self, source: HistoricalOrderFlowSource
    ) -> None:
        assert await source.get_funding_rate("ETHUSDT") == []


async def test_live_fetcher_builds_order_flow_from_history(
    clock: SimClock, source: HistoricalOrderFlowSource
) -> None:
    cache = MarketDataCache([SYMBOL], TechnicalIndicatorCalculator())
    fetcher = LiveOrderFlowFetcher(
        source, cache, OrderFlowCalculator(15, clock), [SYMBOL]
    )

    await fetcher.fetch()

    flow = cache.get_order_flow(SYMBOL)
    assert flow is not None
    assert flow.funding_rate == Decimal("0.0004")
    assert flow.timestamp == clock.now()
    assert flow.long_short_ratio == Decimal(3)
