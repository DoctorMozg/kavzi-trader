import pytest

from kavzi_trader.evals.analyst_record_schema import AnalystRecordSchema
from kavzi_trader.evals.case_result_schema import CaseResultSchema
from kavzi_trader.evals.run_projection_schema import RunProjectionSchema
from kavzi_trader.evals.stage_metrics_schema import StageMetricsSchema
from kavzi_trader.evals.trader_record_schema import TraderRecordSchema


def _result(
    *, analyst_cost: float | None, trader_cost: float = 0.0
) -> CaseResultSchema:
    analyst = (
        AnalystRecordSchema(
            metrics=StageMetricsSchema(
                requests=1, latency_ms=2000.0, cost_usd=analyst_cost
            )
        )
        if analyst_cost is not None
        else None
    )
    trader = (
        TraderRecordSchema(
            metrics=StageMetricsSchema(
                requests=1, latency_ms=4000.0, cost_usd=trader_cost
            )
        )
        if trader_cost
        else None
    )
    return CaseResultSchema(
        case_id="c",
        status="ok",
        label="LONG",
        regime="NORMAL",
        tier="TIER_1",
        analyst=analyst,
        trader=trader,
    )


class TestFromResults:
    def test_free_gate_stops_do_not_dilute_the_per_case_cost(self) -> None:
        results = [
            _result(analyst_cost=0.10, trader_cost=0.30),
            _result(analyst_cost=None),
            _result(analyst_cost=None),
        ]

        projection = RunProjectionSchema.from_results(results, 10, 2, 1.0)

        assert projection.measured_cases == 3
        assert projection.llm_cases == 1
        assert projection.mean_cost_usd == pytest.approx(0.40)
        assert projection.projected_cost_usd == pytest.approx(4.0)

    def test_projection_scales_with_the_reach_fraction(self) -> None:
        results = [_result(analyst_cost=0.10, trader_cost=0.30)]

        full = RunProjectionSchema.from_results(results, 10, 2, 1.0)
        quarter = RunProjectionSchema.from_results(results, 10, 2, 0.25)

        assert quarter.projected_cost_usd == pytest.approx(full.projected_cost_usd / 4)
        assert quarter.projected_time_s == pytest.approx(full.projected_time_s / 4)
        assert quarter.projected_time_s == pytest.approx(6.0 * 10 * 0.25 / 2)

    def test_no_llm_case_measured_projects_nothing(self) -> None:
        projection = RunProjectionSchema.from_results(
            [_result(analyst_cost=None)], 10, 2, 1.0
        )

        assert projection.llm_cases == 0
        assert projection.projected_cost_usd == 0.0
