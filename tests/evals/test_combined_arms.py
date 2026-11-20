import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.combined_arms_report_renderer import CombinedArmsReportRenderer
from kavzi_trader.evals.combined_arms_result_schema import CombinedArmsResultSchema
from kavzi_trader.evals.combined_arms_scorer import CombinedArmsScorer
from kavzi_trader.evals.combined_arms_verdict import CombinedArmsVerdict
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.vol_spike_halving import HOUR, PRICE, VolSpikeHalving
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema

DAYS = pd.date_range("2022-01-01", periods=300, freq="D")
FEE = 0.0005


@pytest.fixture
def data() -> TrendDataSchema:
    rng = np.random.default_rng(7)
    wave = 100 * np.exp(np.cumsum(rng.normal(0.003, 0.03, len(DAYS))))
    closes = pd.DataFrame({"A": wave}, index=DAYS)
    return TrendDataSchema(closes=closes, funding=pd.DataFrame({"A": 0.0}, index=DAYS))


@pytest.fixture
def triggers() -> dict[str, pd.DataFrame]:
    spike_days = DAYS[100::7]
    fired = pd.DataFrame(
        {HOUR: spike_days + pd.Timedelta(hours=10), PRICE: 100.0}, index=spike_days
    )
    return {"A": fired}


@pytest.fixture
def scorer() -> CombinedArmsScorer:
    params = TrendParamsSchema(lookbacks=(20,))
    return CombinedArmsScorer(
        DonchianTrendSignal(params),
        MidExitTrendSignal(params),
        VolSpikeHalving(),
        band=0.2,
        fee=FEE,
        metrics=TrendMetrics(CashRate.constant(0.0)),
    )


@pytest.fixture
def result(
    scorer: CombinedArmsScorer,
    data: TrendDataSchema,
    triggers: dict[str, pd.DataFrame],
) -> CombinedArmsResultSchema:
    return scorer.run(data, triggers, DAYS[40], DAYS[-2])


class TestCombinedArmsScorer:
    def test_arms_without_spikes_equal_their_plain_exit_rule(
        self, scorer: CombinedArmsScorer, data: TrendDataSchema
    ) -> None:
        none = {"A": pd.DataFrame({HOUR: [], PRICE: []}, index=pd.DatetimeIndex([]))}

        result = scorer.run(data, none, DAYS[40], DAYS[-2])

        assert result.halving.daily_net == pytest.approx(result.base.daily_net)
        assert result.mid_halving.daily_net == pytest.approx(result.mid.daily_net)

    def test_mid_exit_changes_the_book_but_not_the_days_scored(
        self, result: CombinedArmsResultSchema
    ) -> None:
        assert len(result.mid.daily_net) == len(result.base.daily_net)
        assert result.mid.daily_net != result.base.daily_net

    def test_halving_is_applied_to_each_arms_own_held_weights(
        self, result: CombinedArmsResultSchema
    ) -> None:
        base_delta = np.array(result.halving.daily_net) - result.base.daily_net
        mid_delta = np.array(result.mid_halving.daily_net) - result.mid.daily_net

        assert result.spike_days_base > 0
        assert not np.allclose(base_delta, mid_delta)

    def test_paired_tests_compare_the_named_arms(
        self, result: CombinedArmsResultSchema
    ) -> None:
        both = result.combined_vs_base
        assert both.base_sharpe == pytest.approx(result.base.net.sharpe)
        assert both.arm_sharpe == pytest.approx(result.mid_halving.net.sharpe)
        gain = result.mid_gain_with_halving
        assert gain.base_sharpe == pytest.approx(result.halving.net.sharpe)


class TestCombinedArmsVerdict:
    def _with_gain_and_cost(
        self, result: CombinedArmsResultSchema, gain: float, cost: float
    ) -> CombinedArmsResultSchema:
        return result.model_copy(
            update={
                "mid_gain_with_halving": result.mid_gain_with_halving.model_copy(
                    update={"difference": gain}
                ),
                "halving_change_under_mid": result.halving_change_under_mid.model_copy(
                    update={"difference": -cost}
                ),
            }
        )

    @pytest.mark.parametrize(
        ("gain", "cost", "expected"),
        [
            (0.2, 0.01, "mid exit + vol-spike halving (unchanged)"),
            (0.2, 0.06, "mid exit only: switch vol_spike off"),
            (0.1, 0.01, "low exit + vol-spike halving: switch exit_rule to low"),
            (
                0.1,
                0.06,
                "low exit, no halving: switch exit_rule to low and vol_spike off",
            ),
            (0.13, 0.05, "mid exit + vol-spike halving (unchanged)"),
        ],
    )
    def test_paper_rule_follows_the_two_thresholds(
        self,
        result: CombinedArmsResultSchema,
        gain: float,
        cost: float,
        expected: str,
    ) -> None:
        scored = self._with_gain_and_cost(result, gain, cost)

        assert CombinedArmsVerdict().paper_rule(scored) == expected

    def test_a_mismatch_with_the_earlier_reports_voids_the_run(
        self, result: CombinedArmsResultSchema
    ) -> None:
        assert CombinedArmsVerdict().reproduction_errors(result)

        report = CombinedArmsReportRenderer("x.md").render(result)

        assert "VOID" in report
        assert "## Decisions" not in report
