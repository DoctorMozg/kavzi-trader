import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.crowding_xs_signal import CrowdingXsSignal
from kavzi_trader.evals.market_alpha import MarketAlpha
from kavzi_trader.evals.positioning_signals import PositioningSignals

DAYS = pd.date_range("2024-01-01", periods=15, freq="D")
SYMBOLS = [f"S{i}" for i in range(9)]


@pytest.fixture
def ranks() -> pd.DataFrame:
    """S0 least crowded ... S8 most, until day 10 reverses the order."""
    values = np.tile(np.arange(9) / 8, (len(DAYS), 1))
    values[10:] = values[10:, ::-1]
    return pd.DataFrame(values, index=DAYS, columns=SYMBOLS)


class TestCrowdingXsSignal:
    def test_longs_least_crowded_third_and_shorts_most_crowded_third(
        self, ranks: pd.DataFrame
    ) -> None:
        book = CrowdingXsSignal(ranks, DAYS[0]).book(ranks.iloc[0])

        assert list(book[book > 0].index) == ["S0", "S1", "S2"]
        assert list(book[book < 0].index) == ["S6", "S7", "S8"]
        assert book.sum() == pytest.approx(0)
        assert book.abs().sum() == pytest.approx(1)

    def test_holds_the_book_until_the_next_weekly_rebalance(
        self, ranks: pd.DataFrame
    ) -> None:
        closes = pd.DataFrame(100.0, index=DAYS, columns=SYMBOLS)

        weights = CrowdingXsSignal(ranks, DAYS[0]).weights(closes)

        # The day-10 reversal is only traded at the day-14 rebalance.
        assert (weights[13] == weights[0]).all()
        assert (weights[14] == -weights[0]).all()

    def test_too_few_names_for_two_legs_of_three_stays_flat(
        self, ranks: pd.DataFrame
    ) -> None:
        sparse = ranks.iloc[0].copy()
        sparse[3:] = np.nan

        book = CrowdingXsSignal(ranks, DAYS[0]).book(sparse)

        assert (book == 0).all()


class TestMarketAlpha:
    def test_recovers_intercept_and_beta(self) -> None:
        rng = np.random.default_rng(6)
        days = pd.date_range("2023-01-01", periods=1500, freq="D")
        market = pd.Series(rng.normal(0, 0.03, len(days)), index=days)
        returns = 0.001 + 1.5 * market + rng.normal(0, 0.005, len(days))

        result = MarketAlpha().regress(returns, market)

        assert result.beta == pytest.approx(1.5, abs=0.02)
        assert result.alpha_annual == pytest.approx(0.365, abs=0.05)
        assert result.alpha_t > 5


class TestCrowdRankLag:
    def test_lag_reads_the_ratio_one_snapshot_older(self) -> None:
        close_ms = 1_000_000_000 + np.arange(1, 6) * 14_400_000 - 1
        at_close = np.array([5.0, 1.0, 5.0, 1.0, 5.0])
        before = 6 - at_close  # 1, 5, 1, 5, 1 five minutes earlier
        frame = pd.DataFrame({"close_time_ms": close_ms})
        metrics = pd.DataFrame(
            {
                "time_ms": np.concatenate([close_ms - 300_000, close_ms]),
                "global_ratio": np.concatenate([before, at_close]),
                "top_position_ratio": 1.0,
            }
        ).sort_values("time_ms", ignore_index=True)

        now = PositioningSignals(history=2).crowd_rank(frame, metrics)
        lagged = PositioningSignals(history=2).crowd_rank(frame, metrics, 300_000)

        np.testing.assert_array_equal(now[1:], [0.5, 1.0, 0.5, 1.0])
        np.testing.assert_array_equal(lagged[1:], [1.0, 0.5, 1.0, 0.5])
