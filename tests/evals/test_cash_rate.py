import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.trend_metrics import TrendMetrics


@pytest.fixture
def cash() -> CashRate:
    months = pd.DatetimeIndex(["2024-01-01", "2024-02-01"])
    return CashRate(pd.Series([0.0365, 0.073], index=months))


class TestCashRate:
    def test_each_day_earns_its_months_rate(self, cash: CashRate) -> None:
        days = pd.DatetimeIndex(["2024-01-31", "2024-02-01", "2024-03-15"])

        daily = cash.daily(days)

        # March has no row yet, so it reuses February's rate.
        assert daily.to_numpy() == pytest.approx([0.0001, 0.0002, 0.0002])

    def test_days_before_the_first_month_are_refused(self, cash: CashRate) -> None:
        with pytest.raises(ValueError, match="cash rates start 2024-01-01"):
            cash.daily(pd.DatetimeIndex(["2023-12-31"]))

    def test_shipped_file_covers_every_scored_window(self) -> None:
        days = pd.date_range("2020-12-15", "2026-10-31")

        daily = CashRate.from_csv().daily(days)

        assert daily.notna().all()
        assert 0.0 < daily.max() * 365 < 0.06


class TestSharpeOverCash:
    def test_returning_exactly_cash_scores_zero_over_cash(self) -> None:
        days = pd.date_range("2024-01-01", periods=400)
        noise = np.random.default_rng(3).normal(0, 0.01, len(days))
        noise -= noise.mean()
        returns = pd.Series(0.05 / 365 + noise, index=days)

        stats = TrendMetrics(CashRate.constant(0.05)).stats(returns)

        assert stats.sharpe is not None
        assert stats.sharpe > 0
        assert stats.sharpe_over_cash == pytest.approx(0.0, abs=1e-9)

    def test_cash_return_compounds_the_daily_rate(self) -> None:
        days = pd.date_range("2024-01-01", periods=365)

        annual = TrendMetrics(CashRate.constant(0.0365)).cash_return(days)

        assert annual == pytest.approx((1 + 0.0001) ** 365 - 1)
