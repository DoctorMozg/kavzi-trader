import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.funding_xs_backtester import FundingXsBacktester
from kavzi_trader.evals.funding_xs_day_schema import FundingXsDaySchema
from kavzi_trader.evals.funding_xs_leg_picker import FundingXsLegPicker
from kavzi_trader.evals.funding_xs_loader import DAY_MS
from kavzi_trader.evals.funding_xs_metrics import FundingXsMetrics
from kavzi_trader.evals.funding_xs_params_schema import FundingXsParamsSchema
from kavzi_trader.evals.funding_xs_run_schema import FundingXsRunSchema
from kavzi_trader.evals.series_cache import TIME, VALUE

T0 = 100 * DAY_MS
SETTLE_MS = 8 * 3_600_000


def _settlements(before: float, later: dict[int, float] | None = None) -> pd.DataFrame:
    """Nine settlements ending 8h before T0, then (offset from T0, rate) extras."""
    times = [T0 - SETTLE_MS * i for i in range(9, 0, -1)]
    rates = [before] * 9
    for offset_ms, rate in (later or {}).items():
        times.append(T0 + offset_ms)
        rates.append(rate)
    return pd.DataFrame({TIME: times, VALUE: rates})


def _prices(a_path: list[float]) -> pd.DataFrame:
    marks = [T0 + i * DAY_MS for i in range(len(a_path))]
    frame = pd.DataFrame(100.0, index=marks, columns=["A", "B", "C", "D"])
    frame["A"] = a_path
    return frame


def _settlements_by_symbol(
    a_later: dict[int, float] | None = None,
    b_later: dict[int, float] | None = None,
) -> dict[str, pd.DataFrame]:
    # A has the highest funding (short), B the lowest (long).
    return {
        "A": _settlements(0.001, a_later),
        "B": _settlements(-0.001, b_later),
        "C": _settlements(0.0001),
        "D": _settlements(-0.0001),
    }


class TestLegPicker:
    def test_shorts_highest_and_longs_lowest(self) -> None:
        scores = {"A": 0.3, "B": -0.2, "C": 0.1, "D": 0.5, "E": -0.4, "F": 0.0}

        legs = FundingXsLegPicker(2).pick(scores)

        assert legs.shorts == ["A", "D"]
        assert legs.longs == ["E", "B"]

    def test_ties_break_by_symbol_name(self) -> None:
        legs = FundingXsLegPicker(1).pick({"B": 0.0, "A": 0.0, "C": 0.0})

        assert (legs.longs, legs.shorts) == (["A"], ["C"])

    def test_too_few_symbols_raises(self) -> None:
        with pytest.raises(ValueError, match="need 6 scored symbols, got 5"):
            FundingXsLegPicker(3).pick(dict.fromkeys("ABCDE", 0.0))


class TestScoreLookAhead:
    def _backtester(self, frame: pd.DataFrame) -> FundingXsBacktester:
        return FundingXsBacktester(
            _prices([100.0, 100.0]), {"A": frame}, FundingXsParamsSchema()
        )

    def test_score_ignores_settlements_at_or_after_rebalance(self) -> None:
        base = self._backtester(_settlements(0.001))
        later = self._backtester(_settlements(0.001, {0: 0.5, SETTLE_MS: 0.9}))

        assert base.scores(T0) == later.scores(T0) == {"A": pytest.approx(0.001)}

    def test_score_uses_only_the_last_nine_settlements(self) -> None:
        older = pd.DataFrame({TIME: [T0 - 10 * SETTLE_MS], VALUE: [9.0]})
        frame = pd.concat([older, _settlements(0.001)], ignore_index=True)

        assert self._backtester(frame).scores(T0)["A"] == pytest.approx(0.001)

    def test_symbol_with_fewer_than_nine_settlements_is_unscored(self) -> None:
        assert self._backtester(_settlements(0.001).iloc[3:]).scores(T0) == {}


class TestFundingSign:
    def _run(
        self, a_later: dict[int, float], b_later: dict[int, float]
    ) -> FundingXsRunSchema:
        params = FundingXsParamsSchema(legs=1, hold_days=1, cost_rate=0.0)
        settlements = _settlements_by_symbol(a_later, b_later)
        return FundingXsBacktester(_prices([100.0, 100.0]), settlements, params).run()

    def test_short_receives_and_long_pays_positive_funding(self) -> None:
        # Weights are +-0.5: short A gets 0.5*0.001, long B pays 0.5*0.002.
        run = self._run({SETTLE_MS: 0.001}, {SETTLE_MS: 0.002})

        assert run.days[0].funding_return == pytest.approx(0.0005 - 0.001)

    def test_negative_funding_pays_the_short_and_credits_the_long(self) -> None:
        run = self._run({SETTLE_MS: -0.001}, {SETTLE_MS: -0.002})

        assert run.days[0].funding_return == pytest.approx(-0.0005 + 0.001)

    def test_settlement_after_the_hold_is_not_counted(self) -> None:
        run = self._run({DAY_MS: 0.5}, {})

        assert run.days[0].funding_return == 0.0


class TestCosts:
    def test_first_rebalance_costs_gross_notional_and_price_adds_up(self) -> None:
        params = FundingXsParamsSchema(legs=1, hold_days=1, cost_rate=0.0005)
        # Short A drops 10%: +0.5 * 0.10 = +0.05; entry trades gross 1.0.
        prices = _prices([100.0, 90.0, 90.0])
        run = FundingXsBacktester(prices, _settlements_by_symbol(), params).run()

        first, second = run.days
        assert first.cost_return == pytest.approx(-0.0005)
        assert first.price_return == pytest.approx(0.05)
        assert first.equity == pytest.approx(1.0 + 0.05 - 0.0005)
        # Same legs again: no weight change, so no cost.
        assert second.cost_return == 0.0
        assert run.turnover == pytest.approx(1.0)
        assert run.rebalances == 2

    def test_zero_cost_rate_charges_nothing(self) -> None:
        params = FundingXsParamsSchema(legs=1, hold_days=1, cost_rate=0.0)
        run = FundingXsBacktester(
            _prices([100.0, 90.0]), _settlements_by_symbol(), params
        ).run()

        assert np.isclose(run.days[0].equity, 1.05)


class TestSharpeOverCash:
    @staticmethod
    def _run(returns: list[float]) -> FundingXsRunSchema:
        start_ms = 1_704_153_600_000  # 2024-01-02 00:00, the mark closing 2024-01-01
        days, equity = [], 1.0
        for i, r in enumerate(returns):
            equity *= 1 + r
            days.append(
                FundingXsDaySchema(
                    day_ms=start_ms + i * DAY_MS,
                    price_return=r,
                    funding_return=0.0,
                    cost_return=0.0,
                    equity=equity,
                )
            )
        return FundingXsRunSchema(
            days=days, rebalances=1, skipped_rebalances=0, turnover=0.0
        )

    def test_subtracting_cash_lowers_the_sharpe_and_zero_cash_changes_nothing(
        self,
    ) -> None:
        returns = list(np.random.default_rng(3).normal(0.0005, 0.005, 400))
        run = self._run(returns)

        no_cash = FundingXsMetrics.summarize(run, CashRate.constant(0.0))
        with_cash = FundingXsMetrics.summarize(run, CashRate.constant(0.05))

        assert no_cash.sharpe_over_cash == pytest.approx(no_cash.sharpe)
        assert with_cash.sharpe == no_cash.sharpe
        assert with_cash.sharpe is not None
        assert with_cash.sharpe_over_cash is not None
        daily_cash = with_cash.sharpe - with_cash.sharpe_over_cash
        # Same vol, mean lower by the daily cash return, annualised by sqrt(365).
        expected = 0.05 / 365 / np.std(returns, ddof=1) * np.sqrt(365)
        assert daily_cash == pytest.approx(expected)
