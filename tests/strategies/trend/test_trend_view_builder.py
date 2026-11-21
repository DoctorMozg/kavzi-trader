from itertools import pairwise

import numpy as np
import pytest

from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.trend_rule_state_schema import (
    TrendRuleStateSchema,
)
from kavzi_trader.strategies.trend.trend_view_builder import DAY_MS, TrendViewBuilder

LOOKBACK = 5
LAST_DAY_MS = 20_000 * DAY_MS


@pytest.fixture
def signal() -> DonchianTrendSignal:
    return DonchianTrendSignal(TrendParamsSchema(lookbacks=(LOOKBACK,), vol_window=3))


@pytest.fixture
def builder(signal: DonchianTrendSignal) -> TrendViewBuilder:
    return TrendViewBuilder(signal, LOOKBACK, days_shown=8)


# Rises to a breakout on day 6, then drifts under the channel low on day 11.
CLOSES = np.array([10, 11, 10, 12, 11, 10, 13, 12, 11, 10.5, 10.4, 9.0])
_DAY_STATES = DonchianTrendSignal(TrendParamsSchema(lookbacks=(LOOKBACK,))).compute(
    CLOSES, 1
)
RULE = TrendRuleStateSchema(
    state=float(_DAY_STATES.signal[-1]), day_states=_DAY_STATES.signal.tolist()
)


class TestTrendViewBuilder:
    def test_next_close_levels_are_the_last_lookback_extremes(
        self, builder: TrendViewBuilder
    ) -> None:
        view = builder.symbol_view("BTCUSDT", CLOSES, RULE, LAST_DAY_MS)

        assert view.entry_level == 12.0
        assert view.exit_level == 9.0
        assert view.close == 9.0

    def test_days_end_at_the_last_closed_day_one_day_apart(
        self, builder: TrendViewBuilder
    ) -> None:
        days = builder.symbol_view("BTCUSDT", CLOSES, RULE, LAST_DAY_MS).days

        assert len(days) == 8
        assert days[-1].day_ms == LAST_DAY_MS
        assert {b.day_ms - a.day_ms for a, b in pairwise(days)} == {DAY_MS}
        assert [d.close for d in days] == list(CLOSES[-8:])

    def test_channel_and_signal_agree_with_the_rule(
        self, builder: TrendViewBuilder
    ) -> None:
        view = builder.symbol_view("BTCUSDT", CLOSES, RULE, LAST_DAY_MS)
        by_close = {d.close: d for d in view.days}

        breakout = by_close[13.0]
        assert breakout.upper == 12.0
        assert breakout.signal == 1.0
        breakdown = view.days[-1]
        assert breakdown.lower == 10.4
        assert breakdown.exit == 10.4
        assert breakdown.signal == 0.0
        assert view.signal == 0.0

    def test_channel_is_none_until_the_lookback_fills(
        self, signal: DonchianTrendSignal
    ) -> None:
        days = (
            TrendViewBuilder(signal, LOOKBACK, days_shown=50)
            .symbol_view("BTCUSDT", CLOSES, RULE, LAST_DAY_MS)
            .days
        )

        assert all(d.upper is None for d in days[:LOOKBACK])
        assert days[LOOKBACK].upper == 12.0

    def test_vol_is_annualised_daily_log_return_std(
        self, builder: TrendViewBuilder
    ) -> None:
        view = builder.symbol_view("BTCUSDT", CLOSES, RULE, LAST_DAY_MS)

        expected = np.std(np.diff(np.log(CLOSES[-4:])), ddof=1) * np.sqrt(365)
        assert view.annual_vol == pytest.approx(expected)

    def test_empty_closes_are_rejected(self, builder: TrendViewBuilder) -> None:
        with pytest.raises(ValueError, match="BTCUSDT: no daily closes"):
            builder.symbol_view("BTCUSDT", np.array([]), RULE, LAST_DAY_MS)

    def test_mid_exit_levels_are_the_channel_midpoint(self) -> None:
        signal = MidExitTrendSignal(
            TrendParamsSchema(lookbacks=(LOOKBACK,), vol_window=3)
        )
        view = TrendViewBuilder(signal, LOOKBACK, days_shown=8).symbol_view(
            "BTCUSDT", CLOSES, RULE, LAST_DAY_MS
        )

        assert view.exit_level == (12.0 + 9.0) / 2
        last = view.days[-1]
        assert last.lower == 10.4
        assert last.exit == (13.0 + 10.4) / 2

    def test_current_signal_is_the_rule_state_after_the_last_check(
        self, builder: TrendViewBuilder
    ) -> None:
        # A 6h close broke out after the last daily close, which was flat.
        rule = RULE.model_copy(update={"state": 1.0})

        view = builder.symbol_view("BTCUSDT", CLOSES, rule, LAST_DAY_MS)

        assert view.signal == 1.0
        assert view.days[-1].signal == 0.0

    def test_states_must_cover_every_close(self, builder: TrendViewBuilder) -> None:
        rule = RULE.model_copy(update={"day_states": RULE.day_states[1:]})

        with pytest.raises(ValueError, match="11 states for 12 closes"):
            builder.symbol_view("BTCUSDT", CLOSES, rule, LAST_DAY_MS)
