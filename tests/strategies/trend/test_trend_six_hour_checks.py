import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.bar_quality_schema import BarQualitySchema
from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.intraday_data_schema import IntradayDataSchema
from kavzi_trader.evals.timing_arm_schema import HOLDOUT_ARM
from kavzi_trader.evals.timing_backtest import TimingBacktest
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)
from kavzi_trader.strategies.tick_schema import StrategyTickSchema
from kavzi_trader.strategies.trend.trend_following_config import (
    TrendFollowingConfigSchema,
)
from kavzi_trader.strategies.trend.trend_following_plugin import (
    RETRY_DELAY_MS,
    TrendFollowingPlugin,
)
from kavzi_trader.strategies.trend.trend_halving_schema import TrendHalvingSchema
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.trend_state_store import TrendStateStore
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer
from tests.strategies.trend.conftest import BASE_MS, SYMBOLS, new_store
from tests.strategies.trend.fake_six_hour_bars import SIX_HOURS_MS, SixHourMarket
from tests.strategies.trend.recording_reporter import RecordingReporter

DAYS = 160
FIRST_SLOT = 4 * 60  # 00:00 of day 60, once the vol window has warmed up
LAST_SLOT = 4 * 150 - 1
SLOTS = range(FIRST_SLOT, LAST_SLOT + 1)


@pytest.fixture
def market() -> SixHourMarket:
    rng = np.random.default_rng(11)
    steps = rng.normal(0.0, 0.0125, (4 * DAYS, len(SYMBOLS)))
    steps += np.array([0.002, -0.0005, 0.001, 0.0])
    return SixHourMarket(
        {s: 100 * np.exp(steps[:, i].cumsum()) for i, s in enumerate(SYMBOLS)}
    )


@pytest.fixture
def config() -> TrendFollowingConfigSchema:
    return TrendFollowingConfigSchema(symbols=SYMBOLS, check_hours=6)


def _plugin(
    config: TrendFollowingConfigSchema, market: SixHourMarket, store: TrendStateStore
) -> TrendFollowingPlugin:
    return TrendFollowingPlugin(config, market.daily, store, intraday=market.intraday)


def _tick(slot: int) -> StrategyTickSchema:
    return StrategyTickSchema(now_ms=BASE_MS + slot * SIX_HOURS_MS + 60_000)


async def _check(
    plugin: TrendFollowingPlugin, slot: int
) -> list[TargetWeightIntentSchema]:
    result = await plugin.tick(_tick(slot))
    intents = [i for i in result.intents if isinstance(i, TargetWeightIntentSchema)]
    for intent in intents:
        plugin.on_enqueued(intent)
    await plugin.flush()
    return intents


async def _held_by_slot(
    plugin: TrendFollowingPlugin, slots: range
) -> dict[int, dict[str, float]]:
    held = dict.fromkeys(SYMBOLS, 0.0)
    by_slot: dict[int, dict[str, float]] = {}
    for slot in slots:
        for intent in await _check(plugin, slot):
            held[intent.symbol] = float(intent.target_weight)
        by_slot[slot] = dict(held)
    return by_slot


class TestCadence:
    async def test_checks_once_per_6h_slot(
        self, config: TrendFollowingConfigSchema, market: SixHourMarket
    ) -> None:
        plugin = _plugin(config, market, new_store())

        first = await plugin.tick(_tick(FIRST_SLOT + 1))
        again = await plugin.tick(_tick(FIRST_SLOT + 1))

        assert first.next_tick_at_ms == _tick(FIRST_SLOT + 2).now_ms
        assert again.intents == []

    async def test_unpublished_bar_retries_without_marking_the_slot(
        self, config: TrendFollowingConfigSchema, market: SixHourMarket
    ) -> None:
        store = new_store()
        plugin = _plugin(config, market, store)
        market.unpublished = 1

        result = await plugin.tick(_tick(FIRST_SLOT))

        assert result.intents == []
        assert result.next_tick_at_ms == _tick(FIRST_SLOT).now_ms + RETRY_DELAY_MS
        assert (await store.load()).last_check_ms is None
        market.unpublished = 0
        await plugin.tick(_tick(FIRST_SLOT))
        stored = await store.load()
        assert stored.last_check_ms == BASE_MS + FIRST_SLOT * SIX_HOURS_MS

    def test_6h_checks_need_an_intraday_provider_and_one_lookback(
        self, config: TrendFollowingConfigSchema, market: SixHourMarket
    ) -> None:
        with pytest.raises(ValueError, match="intraday bar provider"):
            TrendFollowingPlugin(config, market.daily, new_store())
        with pytest.raises(ValueError, match="one lookback"):
            TrendFollowingConfigSchema(check_hours=6, lookbacks=[20, 40])


class TestParityWithTimingBacktest:
    async def test_held_weights_match_the_scored_b_6h_arm(
        self, config: TrendFollowingConfigSchema, market: SixHourMarket
    ) -> None:
        start = pd.Timestamp(BASE_MS, unit="ms")
        bars = pd.DataFrame(
            market.bars, index=pd.date_range(start, periods=4 * DAYS, freq="6h")
        )
        daily = pd.DataFrame(
            {s: market.bars[s][3::4] for s in SYMBOLS},
            index=pd.date_range(start, periods=DAYS, freq="D"),
        )
        backtest = TimingBacktest(
            TrendParamsSchema(lookbacks=(20,)),
            TurnoverBuffer(config.buffer_band),
            TrendPortfolio(0.0),
            TrendMetrics(CashRate.constant(0.0)),
        )
        quality = BarQualitySchema(
            hours=6, listed_days=0, gap_bars=0, day_end_mismatches=0, max_day_end_gap=0
        )
        expected = backtest.held_weights(
            HOLDOUT_ARM,
            TrendDataSchema(closes=daily, funding=daily * 0.0),
            IntradayDataSchema(hours=6, bars=bars, quality=quality),
            start + pd.Timedelta(days=FIRST_SLOT // 4),
            start + pd.Timedelta(days=LAST_SLOT // 4),
        )

        held = await _held_by_slot(_plugin(config, market, new_store()), SLOTS)

        assert list(expected.index) == [
            pd.Timestamp(BASE_MS + s * SIX_HOURS_MS, unit="ms") for s in SLOTS
        ]
        np.testing.assert_allclose(
            np.array([[held[s][sym] for sym in SYMBOLS] for s in SLOTS]),
            expected.to_numpy(),
            rtol=1e-9,
        )
        # Some trades happen between daily closes, or this proves nothing new.
        changed = [s for s in SLOTS if s % 4 and held[s] != held.get(s - 1, held[s])]
        assert changed


class TestReporting:
    async def test_each_check_reports_the_6h_state_and_the_next_check(
        self, config: TrendFollowingConfigSchema, market: SixHourMarket
    ) -> None:
        reporter = RecordingReporter()
        plugin = TrendFollowingPlugin(
            config,
            market.daily,
            new_store(),
            reporter=reporter,
            intraday=market.intraday,
        )

        await _held_by_slot(plugin, SLOTS)

        assert len(reporter.views) == len(SLOTS)
        for slot, view in zip(SLOTS, reporter.views, strict=True):
            assert view.check_hours == 6
            assert view.next_rebalance_ms == _tick(slot + 1).now_ms
            for symbol in view.symbols:
                held = view.held_weights[symbol.symbol]
                assert (symbol.signal == 1.0) == (held > 0)


class TestHalvingBetweenDailyChecks:
    @staticmethod
    def _halving(symbol: str) -> TrendHalvingSchema:
        return TrendHalvingSchema(
            symbol=symbol, hour_ms=0, rv=1.0, threshold=0.5, target_weight=0.01
        )

    async def _halved_after(
        self,
        config: TrendFollowingConfigSchema,
        market: SixHourMarket,
        symbol: str,
        slot: int,
    ) -> tuple[TrendFollowingPlugin, TrendStateStore]:
        """A plugin that ran up to ``slot`` and restarted with ``symbol`` halved."""
        store = new_store()
        await _held_by_slot(_plugin(config, market, store), range(FIRST_SLOT, slot + 1))
        await store.save_halving(self._halving(symbol))
        return _plugin(config, market, store), store

    async def test_quiet_6h_checks_keep_it_and_the_next_day_restores_it(
        self, config: TrendFollowingConfigSchema, market: SixHourMarket
    ) -> None:
        held = await _held_by_slot(_plugin(config, market, new_store()), SLOTS)
        slot, symbol = next(
            (s, sym)
            for s in SLOTS
            if s % 4 == 1
            for sym in SYMBOLS
            if held[s][sym] > 0
            and all(held[s + k][sym] == held[s][sym] for k in (1, 2, 3))
        )
        plugin, store = await self._halved_after(config, market, symbol, slot)

        quiet = [await _check(plugin, s) for s in (slot + 1, slot + 2)]
        midnight = await _check(plugin, slot + 3)

        assert all(i.symbol != symbol for intents in quiet for i in intents)
        (restore,) = [i for i in midnight if i.symbol == symbol]
        assert "restores the vol-spike halving" in restore.reason
        assert (await store.load()).halvings == {}

    async def test_a_6h_exit_ends_it(
        self, config: TrendFollowingConfigSchema, market: SixHourMarket
    ) -> None:
        held = await _held_by_slot(_plugin(config, market, new_store()), SLOTS)
        slot, symbol = next(
            (s, sym)
            for s in SLOTS[1:]
            if s % 4
            for sym in SYMBOLS
            if held[s - 1][sym] > 0 and held[s][sym] == 0
        )
        plugin, store = await self._halved_after(config, market, symbol, slot - 1)

        intents = await _check(plugin, slot)

        (exit_,) = [i for i in intents if i.symbol == symbol]
        assert exit_.target_weight == 0
        assert "ends the vol-spike halving" in exit_.reason
        assert (await store.load()).halvings == {}
