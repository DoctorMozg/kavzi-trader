from datetime import date

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.date_window_schema import DateWindowSchema
from kavzi_trader.evals.scheduled_signal import ScheduledSignal
from kavzi_trader.evals.signal_period_schema import SignalPeriodSchema
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.walk_forward import WalkForward
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

DAYS = pd.date_range("2027-01-01", "2029-12-31", freq="D")
TRAIN_FIRST = date(2027, 1, 1)


class Holds:
    """Always holds one symbol in full."""

    def __init__(self, column: int) -> None:
        self._column = column

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        out = np.zeros(closes.shape)
        out[:, self._column] = 1.0
        return out


def _data(a_drift: dict[int, float], b_drift: dict[int, float]) -> TrendDataSchema:
    """A and B trend by year with a little noise, so each year has a clear winner."""
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 0.005, size=(len(DAYS), 2))
    drift = np.array([[a_drift[d.year], b_drift[d.year]] for d in DAYS])
    closes = pd.DataFrame(
        100 * np.exp(np.cumsum(drift + noise, axis=0)), index=DAYS, columns=["A", "B"]
    )
    return TrendDataSchema(
        closes=closes, funding=pd.DataFrame(0.0, index=DAYS, columns=["A", "B"])
    )


@pytest.fixture
def walk() -> WalkForward:
    return WalkForward(
        {1: Holds(0), 2: Holds(1)},
        TurnoverBuffer(0.0),
        TrendPortfolio(0.0),
        TrendMetrics(CashRate.constant(0.0)),
    )


TEST_YEARS = WalkForward.calendar_years(
    DateWindowSchema(first_day=date(2028, 1, 1), last_day=date(2029, 6, 30))
)


class TestCalendarYears:
    def test_splits_at_year_ends_and_cuts_the_last_year(self) -> None:
        assert [(p.first_day, p.last_day) for p in TEST_YEARS] == [
            (date(2028, 1, 1), date(2028, 12, 31)),
            (date(2029, 1, 1), date(2029, 6, 30)),
        ]


class TestWalkForward:
    def test_each_year_uses_the_best_candidate_on_earlier_years_only(
        self, walk: WalkForward
    ) -> None:
        # A wins 2027, B wins 2028 and 2029 by much more than A won 2027.
        data = _data(
            {2027: 0.002, 2028: -0.003, 2029: -0.003},
            {2027: 0.0, 2028: 0.004, 2029: 0.004},
        )

        result = walk.run(data, TRAIN_FIRST, TEST_YEARS)

        assert [c.lookback for c in result.choices] == [1, 2]
        assert result.out_of_sample.first_day == "2028-01-01"
        assert result.out_of_sample.last_day == "2029-06-30"

    def test_a_years_choice_ignores_that_years_own_data(
        self, walk: WalkForward
    ) -> None:
        base = {2027: 0.002, 2028: 0.0, 2029: 0.0}
        calm_future = walk.run(
            _data(base, {2027: 0.0, 2028: 0.0, 2029: 0.0}), TRAIN_FIRST, TEST_YEARS
        )
        b_booms = walk.run(
            _data(base, {2027: 0.0, 2028: 0.01, 2029: 0.0}), TRAIN_FIRST, TEST_YEARS
        )

        assert calm_future.choices[0].lookback == b_booms.choices[0].lookback == 1

    def test_test_years_must_start_after_training(self, walk: WalkForward) -> None:
        data = _data(
            {2027: 0.0, 2028: 0.0, 2029: 0.0}, {2027: 0.0, 2028: 0.0, 2029: 0.0}
        )

        with pytest.raises(ValueError, match="must start after training"):
            walk.run(data, date(2028, 1, 1), TEST_YEARS)


def test_scheduled_signal_hands_each_return_day_to_its_period() -> None:
    closes = pd.DataFrame(
        1.0, index=pd.date_range("2028-12-29", periods=5), columns=["A", "B"]
    )
    signal = ScheduledSignal(
        [
            SignalPeriodSchema(
                first_day=date(2028, 12, 30),
                last_day=date(2028, 12, 31),
                signal=Holds(0),
            ),
            SignalPeriodSchema(
                first_day=date(2029, 1, 1), last_day=date(2029, 1, 2), signal=Holds(1)
            ),
        ]
    )

    weights = signal.weights(closes)

    # Rows are closes Dec 29..Jan 2; each earns the next day, Jan 3 is unscheduled.
    np.testing.assert_array_equal(weights[:, 0], [1, 1, 0, 0, 0])
    np.testing.assert_array_equal(weights[:, 1], [0, 0, 1, 1, 0])
