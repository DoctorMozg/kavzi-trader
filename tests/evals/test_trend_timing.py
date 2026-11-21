from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.bar_quality_schema import BarQualitySchema
from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.intraday_data_loader import IntradayDataLoader
from kavzi_trader.evals.intraday_data_schema import IntradayDataSchema
from kavzi_trader.evals.timing_arm_schema import TIMING_ARMS, TimingArmSchema
from kavzi_trader.evals.timing_backtest import TimingBacktest
from kavzi_trader.evals.timing_verdict import REPRODUCED, TimingVerdict
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.validation.paired_sharpe_schema import PairedSharpeSchema
from kavzi_trader.evals.validation.paired_sharpe_test import PairedSharpeTest
from kavzi_trader.evals.weight_backtest import WeightBacktest
from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

PARAMS = TrendParamsSchema(lookbacks=(20,))
FEE = 0.0005
QUALITY = BarQualitySchema(
    hours=24, listed_days=0, gap_bars=0, day_end_mismatches=0, max_day_end_gap=0.0
)


def _data(closes: np.ndarray, start: str = "2027-01-01") -> TrendDataSchema:
    index = pd.date_range(start, periods=len(closes), freq="D")
    frame = pd.DataFrame(
        closes, index=index, columns=[f"S{i}" for i in range(closes.shape[1])]
    )
    funding = pd.DataFrame(0.0001, index=index, columns=frame.columns)
    return TrendDataSchema(closes=frame, funding=funding)


def _bars(
    data: TrendDataSchema,
    hours: int,
    moves: dict[tuple[int, int], float] | None = None,
) -> IntradayDataSchema:
    """Each bar closes at the previous day's close, the last at its own day's.

    ``moves`` sets chosen (day, bar) closes of symbol 0.
    """
    per_day = 24 // hours
    daily = data.closes.to_numpy()
    held = np.vstack([daily[:1], daily[:-1]])
    prices = np.repeat(held, per_day, axis=0)
    prices[per_day - 1 :: per_day] = daily
    for (day, bar), price in (moves or {}).items():
        prices[day * per_day + bar, 0] = price
    index = pd.date_range(data.closes.index[0], periods=len(prices), freq=f"{hours}h")
    frame = pd.DataFrame(prices, index=index, columns=data.closes.columns)
    return IntradayDataSchema(hours=hours, bars=frame, quality=QUALITY)


def _backtest(fee: float = FEE) -> TimingBacktest:
    return TimingBacktest(
        PARAMS,
        TurnoverBuffer(0.2),
        TrendPortfolio(fee),
        TrendMetrics(CashRate.constant(0.0)),
    )


def _random_walk(days: int = 200, symbols: int = 2) -> TrendDataSchema:
    steps = np.random.default_rng(3).normal(0.002, 0.03, size=(days, symbols))
    return _data(100 * np.exp(np.cumsum(steps, axis=0)))


FIRST = pd.Timestamp("2027-03-01")
LAST = pd.Timestamp("2027-06-30")


class TestDailyChecksReproduceTheBase:
    @pytest.mark.parametrize("approach", ["A", "B"])
    def test_24h_bars_give_the_base_result(self, approach: Literal["A", "B"]) -> None:
        data = _random_walk()
        base_backtest = WeightBacktest(
            MidExitTrendSignal(PARAMS),
            TurnoverBuffer(0.2),
            TrendPortfolio(FEE),
            TrendMetrics(CashRate.constant(0.0)),
        )
        base = base_backtest.run(data, FIRST, LAST)
        held = base_backtest.held_weights(data, FIRST, LAST).to_numpy()
        arm = TimingArmSchema(approach=approach, hours=24)

        scored = _backtest().run(arm, data, _bars(data, 24), FIRST, LAST)

        result = scored.result
        np.testing.assert_allclose(result.daily_net, base.daily_net, atol=1e-12)
        assert result.turnover_per_year == pytest.approx(base.turnover_per_year)
        assert result.cost_drag == pytest.approx(base.cost_drag)
        assert result.funding_drag == pytest.approx(base.funding_drag)
        assert result.benchmark == base.benchmark
        assert scored.trades_per_year == pytest.approx(
            TimingBacktest.trades_per_year(held, base.days)
        )
        assert base.turnover_per_year > 0

    def test_intraday_checks_with_no_trade_leave_the_day_return_alone(self) -> None:
        # Bars that never cross a level and a weight that never changes: only
        # the daily path can move the book, so 4h checks must not alter it.
        data = _data(np.full((80, 1), 100.0) + np.linspace(0, 0.5, 80)[:, None])
        flat = _backtest().run(
            TimingArmSchema(approach="B", hours=24), data, _bars(data, 24), FIRST, LAST
        )
        fast = _backtest().run(
            TimingArmSchema(approach="B", hours=4), data, _bars(data, 4), FIRST, LAST
        )

        np.testing.assert_allclose(
            fast.result.daily_net, flat.result.daily_net, atol=1e-12
        )


class TestIntradayEntry:
    # Flat at 100 for 60 days, so the 20-day high is 100 and vol is zero (2x cap).
    ENTRY_DAY = 60

    @pytest.fixture
    def data(self) -> TrendDataSchema:
        closes = np.full((80, 1), 100.0)
        # The day's own close is far above every level; a leak into its bars' levels
        # would lift the entry level past the 4h close.
        closes[self.ENTRY_DAY :] = 150.0
        return _data(closes)

    def test_a_4h_close_above_the_daily_entry_level_enters_before_the_day_closes(
        self, data: TrendDataSchema
    ) -> None:
        bars = _bars(data, 4, {(self.ENTRY_DAY, 0): 101.0})
        day = data.closes.index[self.ENTRY_DAY]

        held = _backtest().held_weights(
            TimingArmSchema(approach="B", hours=4),
            data,
            bars,
            day - pd.Timedelta(days=5),
            day + pd.Timedelta(days=5),
        )

        assert held.loc[day, "S0"] == 0
        assert held.loc[day + pd.Timedelta(hours=4), "S0"] == pytest.approx(2.0)

    def test_the_daily_check_waits_for_the_close(self, data: TrendDataSchema) -> None:
        day = data.closes.index[self.ENTRY_DAY]

        held = _backtest().held_weights(
            TimingArmSchema(approach="B", hours=24),
            data,
            _bars(data, 24),
            day - pd.Timedelta(days=5),
            day + pd.Timedelta(days=5),
        )

        # The 24h checkpoints are day closes: flat at the 59th, long at the 60th.
        assert held.loc[day, "S0"] == 0
        assert held.loc[day + pd.Timedelta(days=1), "S0"] > 0

    def test_commission_is_charged_on_the_intraday_trade_in_its_own_day(
        self, data: TrendDataSchema
    ) -> None:
        bars = _bars(data, 4, {(self.ENTRY_DAY, 0): 101.0})
        arm = TimingArmSchema(approach="B", hours=4)
        first = data.closes.index[self.ENTRY_DAY - 5]
        last = data.closes.index[self.ENTRY_DAY + 5]

        free = _backtest(0.0).run(arm, data, bars, first, last).result
        paid = _backtest(FEE).run(arm, data, bars, first, last).result

        by_day = np.array(free.daily_net) - np.array(paid.daily_net)
        # Entering 2.0 at the 04:00 close costs FEE x 2.0 on the entry day itself.
        assert by_day[5] == pytest.approx(FEE * 2.0)
        assert by_day[:5] == pytest.approx(0.0)
        assert paid.cost_drag > 0


class TestNoLookahead:
    @pytest.mark.parametrize("approach", ["A", "B"])
    @pytest.mark.parametrize("hours", [12, 4])
    def test_prices_after_the_window_change_nothing(
        self, approach: Literal["A", "B"], hours: int
    ) -> None:
        full = _random_walk(days=200)
        cut = 150
        short = TrendDataSchema(
            closes=full.closes.iloc[:cut], funding=full.funding.iloc[:cut]
        )
        per_day = 24 // hours
        full_bars = _bars(full, hours)
        short_bars = IntradayDataSchema(
            hours=hours,
            bars=full_bars.bars.iloc[: cut * per_day],
            quality=QUALITY,
        )
        arm = TimingArmSchema(approach=approach, hours=hours)
        last = full.closes.index[cut - 1]

        on_full = _backtest().run(arm, full, full_bars, FIRST, last).result
        on_short = _backtest().run(arm, short, short_bars, FIRST, last).result

        assert on_full.daily_net == on_short.daily_net


class TestArms:
    def test_six_arms_two_approaches_three_timings(self) -> None:
        assert [a.label for a in TIMING_ARMS] == [
            "A-12h",
            "A-6h",
            "A-4h",
            "B-12h",
            "B-6h",
            "B-4h",
        ]

    def test_bars_must_divide_the_day(self) -> None:
        with pytest.raises(ValueError, match="divide a UTC day"):
            TimingArmSchema(approach="A", hours=5)

    def test_mismatched_bars_are_rejected(self) -> None:
        data = _random_walk()
        with pytest.raises(ValueError, match="do not fit arm"):
            _backtest().run(
                TimingArmSchema(approach="A", hours=6),
                data,
                _bars(data, 12),
                FIRST,
                LAST,
            )

    def test_arm_with_several_lookbacks_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="one lookback"):
            TimingBacktest(
                TrendParamsSchema(lookbacks=(20, 40)),
                TurnoverBuffer(0.2),
                TrendPortfolio(FEE),
                TrendMetrics(CashRate.constant(0.0)),
            )


def _paired(lower: float, difference: float) -> PairedSharpeSchema:
    return PairedSharpeSchema(
        base_sharpe=0.5,
        arm_sharpe=0.5 + difference,
        difference=difference,
        lower=lower,
        upper=lower + 1,
        p_not_better=0.1,
        resamples=5000,
        mean_block_days=20,
    )


class TestBonferroniVerdict:
    verdict = TimingVerdict()

    def test_adjusted_level_splits_ten_percent_over_six_arms(self) -> None:
        assert self.verdict.adjusted_confidence == pytest.approx(1 - 0.10 / 6)

    def test_fresh_needs_a_lower_bound_strictly_above_zero(self) -> None:
        assert not self.verdict.fresh_passes(_paired(0.0, 0.3))
        assert not self.verdict.fresh_passes(_paired(-0.001, 0.3))
        assert self.verdict.fresh_passes(_paired(1e-9, 0.3))

    def test_trading_needs_a_difference_of_zero_or_more(self) -> None:
        assert self.verdict.trading_passes(_paired(-1.0, 0.0))
        assert not self.verdict.trading_passes(_paired(-1.0, -1e-9))

    @pytest.mark.parametrize(
        ("universe", "sharpe", "ok"),
        [
            ("fresh", 0.688, True),
            ("fresh", 0.6899, True),
            ("fresh", 0.6921, False),
            ("trading", 0.9031, True),
            ("trading", 0.9071, False),
            ("trading", None, False),
        ],
    )
    def test_base_must_reproduce_within_the_tolerance(
        self, universe: str, sharpe: float | None, ok: bool
    ) -> None:
        error = self.verdict.reproduction_error(universe, sharpe)

        assert (error is None) is ok
        assert set(REPRODUCED) == {"fresh", "trading"}

    def test_the_adjusted_interval_is_wider_than_the_90_percent_one(self) -> None:
        rng = np.random.default_rng(4)
        base = list(rng.normal(0.0005, 0.02, 600))
        arm = [r + 0.001 + rng.normal(0, 0.01) for r in base]

        plain = PairedSharpeTest(resamples=500).compare(base, arm)
        adjusted = PairedSharpeTest(
            resamples=500, confidence=self.verdict.adjusted_confidence
        ).compare(base, arm)

        assert adjusted.lower < plain.lower < plain.upper < adjusted.upper
        assert adjusted.confidence == pytest.approx(0.98333, abs=1e-5)

    def test_a_bar_set_that_disagrees_with_the_daily_bars_voids_the_run(self) -> None:
        bad = QUALITY.model_copy(update={"listed_days": 1000, "day_end_mismatches": 2})
        good = QUALITY.model_copy(update={"listed_days": 1000, "day_end_mismatches": 1})

        assert self.verdict.quality_error([good]) is None
        assert "2/1000" in (self.verdict.quality_error([good, bad]) or "")


HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
START_MS = 1_609_459_200_000  # 2021-01-01


def _hourly(days: int, skip: set[int] | None = None) -> pd.DataFrame:
    hours = np.arange(days * 24)
    frame = pd.DataFrame(
        {"open_time_ms": START_MS + hours * HOUR_MS, "close": 100.0 + hours}
    )
    return frame.drop(index=sorted(skip or set())).reset_index(drop=True)


def _daily_from_hourly(days: int) -> pd.DataFrame:
    closes = 100.0 + np.arange(days) * 24 + 23
    return pd.DataFrame({"A": closes}, index=pd.date_range("2021-01-01", periods=days))


class TestIntradayDataLoader:
    loader = IntradayDataLoader(ArchiveSeries(Path("unused")))

    def test_bars_close_on_their_last_hour(self) -> None:
        built = self.loader.build({"A": _hourly(2)}, _daily_from_hourly(2), 12)

        assert built.bars["A"].tolist() == [111.0, 123.0, 135.0, 147.0]
        assert built.bars.index[1] == pd.Timestamp("2021-01-01 12:00")
        assert built.quality.day_end_mismatches == 0

    def test_a_bar_missing_an_hour_carries_the_previous_close(self) -> None:
        # Hour 11 missing makes the 06-12 bar incomplete.
        built = self.loader.build(
            {"A": _hourly(2, skip={11})}, _daily_from_hourly(2), 6
        )

        assert built.bars["A"].iloc[:3].tolist() == [105.0, 105.0, 117.0]
        assert built.quality.gap_bars == 1

    def test_the_last_bar_of_a_day_is_the_daily_close(self) -> None:
        daily = _daily_from_hourly(2)
        daily.iloc[0, 0] = 123.0 + 1e-3

        built = self.loader.build({"A": _hourly(2)}, daily, 4)

        assert built.bars["A"].iloc[5] == daily.iloc[0, 0]
        assert built.quality.day_end_mismatches == 1
        assert built.quality.max_day_end_gap == pytest.approx(1e-3 / 123, rel=1e-3)

    def test_unlisted_days_have_no_bars(self) -> None:
        daily = _daily_from_hourly(3)
        daily.iloc[1, 0] = np.nan

        built = self.loader.build({"A": _hourly(3)}, daily, 12)

        assert built.bars["A"].iloc[2:4].isna().all()
        assert built.quality.listed_days == 2

    def test_bars_that_do_not_divide_a_day_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="divide a UTC day"):
            self.loader.build({"A": _hourly(1)}, _daily_from_hourly(1), 5)
