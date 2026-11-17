import numpy as np

from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_following_config import (
    TrendFollowingConfigSchema,
)
from kavzi_trader.strategies.trend.trend_following_plugin import (
    DAY_MS,
    REBALANCE_DELAY_MS,
    RETRY_DELAY_MS,
    TrendFollowingPlugin,
)
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.trend_state_store import TrendStateStore
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer
from tests.strategies.trend.conftest import (
    BASE_MS,
    FIRST_DAY,
    SYMBOLS,
    new_store,
    tick_at,
)
from tests.strategies.trend.fake_daily_bars import FakeDailyBars


async def run_day(
    plugin: TrendFollowingPlugin, bars: FakeDailyBars, day: int
) -> list[TargetWeightIntentSchema]:
    """Ticks one day and acknowledges every intent as the loop would."""
    bars.upto = day
    result = await plugin.tick(tick_at(day))
    intents = [i for i in result.intents if isinstance(i, TargetWeightIntentSchema)]
    for intent in intents:
        plugin.on_enqueued(intent)
    await plugin.flush()
    return intents


class TestCadence:
    async def test_next_tick_is_next_midnight_plus_60s(
        self, plugin: TrendFollowingPlugin, bars: FakeDailyBars
    ) -> None:
        bars.upto = FIRST_DAY
        result = await plugin.tick(tick_at(FIRST_DAY))

        expected = BASE_MS + (FIRST_DAY + 1) * DAY_MS + REBALANCE_DELAY_MS
        assert result.next_tick_at_ms == expected

    async def test_late_evening_start_still_targets_next_midnight(
        self, plugin: TrendFollowingPlugin, bars: FakeDailyBars
    ) -> None:
        bars.upto = FIRST_DAY
        evening = BASE_MS + FIRST_DAY * DAY_MS + DAY_MS - 1_000
        result = await plugin.tick(
            tick_at(FIRST_DAY).model_copy(update={"now_ms": evening})
        )

        assert result.next_tick_at_ms == BASE_MS + (FIRST_DAY + 1) * DAY_MS + 60_000


class TestRebalance:
    async def test_first_tick_catches_up_immediately(
        self, plugin: TrendFollowingPlugin, bars: FakeDailyBars
    ) -> None:
        intents = await run_day(plugin, bars, FIRST_DAY + 30)

        assert intents
        assert all(i.created_at_ms == tick_at(FIRST_DAY + 30).now_ms for i in intents)

    async def test_second_tick_same_day_does_nothing(
        self, plugin: TrendFollowingPlugin, bars: FakeDailyBars
    ) -> None:
        await run_day(plugin, bars, FIRST_DAY + 30)
        calls = bars.calls

        again = await plugin.tick(tick_at(FIRST_DAY + 30))

        assert again.intents == []
        assert bars.calls == calls

    async def test_only_changed_symbols_emit_intents(
        self, plugin: TrendFollowingPlugin, bars: FakeDailyBars
    ) -> None:
        total = 0
        for day in range(FIRST_DAY, FIRST_DAY + 60):
            total += len(await run_day(plugin, bars, day))

        assert 0 < total < 60 * len(SYMBOLS)

    async def test_intent_ids_are_unique_and_carry_config(
        self,
        plugin: TrendFollowingPlugin,
        bars: FakeDailyBars,
        config: TrendFollowingConfigSchema,
    ) -> None:
        intents = [
            i
            for day in range(FIRST_DAY, FIRST_DAY + 60)
            for i in await run_day(plugin, bars, day)
        ]

        ids = [i.intent_id for i in intents]
        assert len(ids) == len(set(ids))
        assert all(i.disaster_stop_pct == config.disaster_stop_pct for i in intents)
        assert all(i.expires_at_ms - i.created_at_ms == 3_600_000 for i in intents)

    async def test_failed_fetch_retries_without_marking_the_day(
        self, plugin: TrendFollowingPlugin, bars: FakeDailyBars
    ) -> None:
        bars.upto = 5  # too little history for the rule
        first = await plugin.tick(tick_at(5))

        assert first.intents == []
        assert first.next_tick_at_ms == tick_at(5).now_ms + RETRY_DELAY_MS

        bars.upto = FIRST_DAY + 30
        assert (await plugin.tick(tick_at(5))).intents


class TestParityWithBacktest:
    async def test_buffered_weights_match_eval_signal_and_buffer(
        self,
        plugin: TrendFollowingPlugin,
        bars: FakeDailyBars,
        closes: dict[str, np.ndarray],
        config: TrendFollowingConfigSchema,
    ) -> None:
        signal = DonchianTrendSignal(TrendParamsSchema(lookbacks=(20,)))
        targets = np.column_stack(
            [signal.compute(closes[s], len(SYMBOLS)).weight for s in SYMBOLS]
        )
        expected = TurnoverBuffer(config.buffer_band).apply(targets[FIRST_DAY:])

        held = dict.fromkeys(SYMBOLS, 0.0)
        for offset, day in enumerate(range(FIRST_DAY, len(closes[SYMBOLS[0]]))):
            for intent in await run_day(plugin, bars, day):
                held[intent.symbol] = float(intent.target_weight)
            np.testing.assert_array_equal(
                np.array([held[s] for s in SYMBOLS]), expected[offset]
            )
        assert expected.any()


class TestPersistence:
    async def test_restart_same_day_does_not_rebalance_again(
        self,
        plugin: TrendFollowingPlugin,
        bars: FakeDailyBars,
        config: TrendFollowingConfigSchema,
        store: TrendStateStore,
    ) -> None:
        await run_day(plugin, bars, FIRST_DAY + 30)

        restarted = TrendFollowingPlugin(config, bars, store)
        result = await restarted.tick(tick_at(FIRST_DAY + 30))

        assert result.intents == []

    async def test_restart_reloads_weights_and_matches_uninterrupted_run(
        self,
        plugin: TrendFollowingPlugin,
        bars: FakeDailyBars,
        config: TrendFollowingConfigSchema,
        store: TrendStateStore,
    ) -> None:
        reference_bars = FakeDailyBars(bars._closes)
        reference = TrendFollowingPlugin(config, reference_bars, new_store())
        # Two plugins on separate Redis state, one restarted midway.
        days = range(FIRST_DAY, FIRST_DAY + 40)
        for day in days[:-1]:
            await run_day(reference, reference_bars, day)
            await run_day(plugin, bars, day)
        restarted = TrendFollowingPlugin(config, bars, store)

        resumed = await run_day(restarted, bars, days[-1])
        expected = await run_day(reference, reference_bars, days[-1])

        assert [(i.symbol, i.target_weight) for i in resumed] == [
            (i.symbol, i.target_weight) for i in expected
        ]
        stored = await store.load()
        assert stored.weights
        assert stored.last_rebalance_day is not None


class RecordingReviewer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def review_entry(self, symbol: str, as_of_ms: int) -> None:
        self.calls.append((symbol, as_of_ms))


class TestShadowReview:
    async def test_reviews_only_flat_to_long_and_leaves_intents_unchanged(
        self,
        plugin: TrendFollowingPlugin,
        bars: FakeDailyBars,
        config: TrendFollowingConfigSchema,
    ) -> None:
        reviewer = RecordingReviewer()
        reviewed_bars = FakeDailyBars(bars._closes)
        reviewed = TrendFollowingPlugin(config, reviewed_bars, new_store(), reviewer)
        held: dict[str, float] = {}
        entries: list[tuple[str, int]] = []
        for day in range(FIRST_DAY, FIRST_DAY + 60):
            plain = await run_day(plugin, bars, day)
            shadowed = await run_day(reviewed, reviewed_bars, day)
            assert [(i.symbol, i.target_weight) for i in shadowed] == [
                (i.symbol, i.target_weight) for i in plain
            ]
            for intent in plain:
                if held.get(intent.symbol, 0.0) == 0.0 and intent.target_weight > 0:
                    entries.append((intent.symbol, intent.created_at_ms))
                held[intent.symbol] = float(intent.target_weight)

        assert entries
        assert reviewer.calls == entries
