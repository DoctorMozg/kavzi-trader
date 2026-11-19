from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kavzi_trader.domain.state_schemas import (
    AccountStateSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)
from kavzi_trader.strategies.tick_schema import StrategyTickSchema
from kavzi_trader.strategies.trend.hourly_variance_schema import HourlyVarianceSchema
from kavzi_trader.strategies.trend.hourly_variance_store import HourlyVarianceStore
from kavzi_trader.strategies.trend.trend_following_config import (
    TrendFollowingConfigSchema,
)
from kavzi_trader.strategies.trend.trend_following_plugin import (
    DAY_MS,
    TrendFollowingPlugin,
)
from kavzi_trader.strategies.trend.trend_state_store import TrendStateStore
from kavzi_trader.strategies.trend.vol_spike_config import VolSpikeConfigSchema
from kavzi_trader.strategies.trend.vol_spike_monitor import HOUR_MS, VolSpikeMonitor
from tests.strategies.trend.conftest import BASE_MS, FIRST_DAY
from tests.strategies.trend.fake_daily_bars import FakeDailyBars
from tests.strategies.trend.recording_reporter import RecordingReporter

DAY = FIRST_DAY + 30
DAY_START_MS = BASE_MS + DAY * DAY_MS
SPIKE_MS = DAY_START_MS + 10 * HOUR_MS
PRICE = 100.0
EQUITY = Decimal(10_000)
QUANTITY = Decimal(10)
AT = datetime(2026, 11, 20, tzinfo=UTC)


class FakeHours:
    """Calm hours, except the ones in ``spikes``."""

    def __init__(self) -> None:
        self.spikes: set[int] = set()
        self.calls = 0

    async def hours(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> list[HourlyVarianceSchema]:
        self.calls += 1
        return [
            HourlyVarianceSchema(
                hour_ms=h,
                rv=1.0 if h in self.spikes else 1e-4 * (1 + h // HOUR_MS % 7),
                close=PRICE,
            )
            for h in range(start_ms, end_ms, HOUR_MS)
        ]


def at_hour(hour: int, positions: list[PositionSchema]) -> StrategyTickSchema:
    """A tick a minute after ``hour`` of DAY closes."""
    return StrategyTickSchema(
        now_ms=DAY_START_MS + (hour + 1) * HOUR_MS + 60_000,
        account=AccountStateSchema(
            total_balance_usdt=EQUITY,
            available_balance_usdt=EQUITY,
            locked_balance_usdt=Decimal(0),
            peak_balance=EQUITY,
            updated_at=AT,
        ),
        positions=positions,
    )


def long(symbol: str) -> PositionSchema:
    return PositionSchema(
        id=f"pos-{symbol}",
        symbol=symbol,
        side="LONG",
        quantity=QUANTITY,
        entry_price=Decimal(repr(PRICE)),
        stop_loss=Decimal(70),
        take_profit=None,
        current_stop_loss=Decimal(70),
        management_config=PositionManagementConfigSchema(),
        strategy="trend_following",
        exit_policy="SIGNAL",
        leverage=2,
        initial_margin=Decimal(500),
        opened_at=AT,
        updated_at=AT,
    )


@pytest.fixture
def hours() -> FakeHours:
    source = FakeHours()
    source.spikes.add(SPIKE_MS)
    return source


@pytest.fixture
def reporter() -> RecordingReporter:
    return RecordingReporter()


def make_plugin(
    config: TrendFollowingConfigSchema,
    bars: FakeDailyBars,
    store: TrendStateStore,
    hours: FakeHours,
    reporter: RecordingReporter,
) -> TrendFollowingPlugin:
    monitor = VolSpikeMonitor(
        VolSpikeConfigSchema(history_hours=48, min_history_hours=24),
        hours,
        HourlyVarianceStore(RedisStateClient.in_memory()),
    )
    return TrendFollowingPlugin(config, bars, store, reporter=reporter, spikes=monitor)


@pytest.fixture
def plugin(
    config: TrendFollowingConfigSchema,
    bars: FakeDailyBars,
    store: TrendStateStore,
    hours: FakeHours,
    reporter: RecordingReporter,
) -> TrendFollowingPlugin:
    return make_plugin(config, bars, store, hours, reporter)


async def tick(
    plugin: TrendFollowingPlugin, ctx: StrategyTickSchema
) -> list[TargetWeightIntentSchema]:
    """Ticks and acknowledges every intent as the strategy loop would."""
    result = await plugin.tick(ctx)
    intents = [i for i in result.intents if isinstance(i, TargetWeightIntentSchema)]
    for intent in intents:
        plugin.on_enqueued(intent)
    await plugin.flush()
    return intents


async def rebalance(plugin: TrendFollowingPlugin, bars: FakeDailyBars, day: int) -> str:
    """Rebalances ``day`` and returns a symbol the rule holds afterwards."""
    bars.upto = day
    rebalanced = await tick(
        plugin, StrategyTickSchema(now_ms=BASE_MS + day * DAY_MS + 60_000)
    )
    held = [i.symbol for i in rebalanced if i.target_weight > 0]
    assert held
    return held[0]


class TestVolSpikeHalving:
    async def test_first_spike_halves_the_position_once(
        self,
        plugin: TrendFollowingPlugin,
        bars: FakeDailyBars,
        store: TrendStateStore,
    ) -> None:
        symbol = await rebalance(plugin, bars, DAY)
        weight = (await store.load()).weights[symbol]

        assert await tick(plugin, at_hour(9, [long(symbol)])) == []
        (halve,) = await tick(plugin, at_hour(10, [long(symbol)]))
        later = await tick(plugin, at_hour(11, [long(symbol)]))

        assert halve.symbol == symbol
        assert halve.intent_id.endswith(":halve")
        assert halve.target_weight == QUANTITY * Decimal(repr(PRICE)) / 2 / EQUITY
        assert "vol spike 10:00 UTC" in halve.reason
        assert later == []
        state = await store.load()
        assert state.weights[symbol] == weight
        assert state.halvings[symbol].hour_ms == SPIKE_MS

    async def test_flat_book_fetches_nothing(
        self, plugin: TrendFollowingPlugin, bars: FakeDailyBars, hours: FakeHours
    ) -> None:
        await rebalance(plugin, bars, DAY)

        assert await tick(plugin, at_hour(10, [])) == []
        assert hours.calls == 0

    async def test_next_rebalance_restores_the_rule_weight(
        self,
        plugin: TrendFollowingPlugin,
        bars: FakeDailyBars,
        store: TrendStateStore,
    ) -> None:
        symbol = await rebalance(plugin, bars, DAY)
        await tick(plugin, at_hour(10, [long(symbol)]))

        bars.upto = DAY + 1
        intents = await tick(
            plugin, StrategyTickSchema(now_ms=BASE_MS + (DAY + 1) * DAY_MS + 60_000)
        )

        (restore,) = [i for i in intents if i.symbol == symbol]
        assert "restores the vol-spike halving" in restore.reason
        assert float(restore.target_weight) == (await store.load()).weights[symbol]
        assert (await store.load()).halvings == {}

    async def test_restart_keeps_the_halving(
        self,
        config: TrendFollowingConfigSchema,
        plugin: TrendFollowingPlugin,
        bars: FakeDailyBars,
        store: TrendStateStore,
        hours: FakeHours,
        reporter: RecordingReporter,
    ) -> None:
        symbol = await rebalance(plugin, bars, DAY)
        await tick(plugin, at_hour(10, [long(symbol)]))

        restarted = make_plugin(config, bars, store, hours, reporter)

        assert await tick(restarted, at_hour(11, [long(symbol)])) == []

    async def test_ticks_hourly_while_halving_is_on(
        self, plugin: TrendFollowingPlugin, bars: FakeDailyBars
    ) -> None:
        bars.upto = DAY
        result = await plugin.tick(StrategyTickSchema(now_ms=DAY_START_MS + 60_000))

        assert result.next_tick_at_ms == DAY_START_MS + HOUR_MS + 60_000

    async def test_dashboard_sees_the_reading_and_the_halving(
        self,
        plugin: TrendFollowingPlugin,
        bars: FakeDailyBars,
        reporter: RecordingReporter,
    ) -> None:
        symbol = await rebalance(plugin, bars, DAY)
        await tick(plugin, at_hour(10, [long(symbol)]))

        (halving,) = reporter.halvings
        view = reporter.views[-1]
        assert not view.rebalanced
        assert view.vol_spike is not None
        assert view.spikes[symbol].hour_ms == SPIKE_MS
        assert view.halvings == {symbol: halving}
        assert halving.target_weight == pytest.approx(0.05)
