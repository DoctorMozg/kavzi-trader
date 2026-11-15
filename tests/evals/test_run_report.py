from typing import ClassVar

import pytest

from kavzi_trader.evals.confusion_metrics import ConfusionMetrics
from kavzi_trader.evals.stage_metrics_schema import StageMetricsSchema
from kavzi_trader.evals.stage_ops import StageOps
from kavzi_trader.evals.token_usage_schema import TokenUsageSchema
from tests.evals.report_fixtures import case_for, flat_frame, joined, trader_record


@pytest.fixture
def case():
    return case_for(flat_frame())


class TestFinalAction:
    @pytest.mark.parametrize("stopped_at", ["scout", "analyst_skipped", "analyst_gate"])
    def test_stages_before_the_trader_mean_no_trade(self, case, stopped_at) -> None:
        assert joined(case, stopped_at).final_action == "NO_TRADE"

    @pytest.mark.parametrize(
        ("stopped_at", "trader"),
        [
            ("trader_gate", trader_record("LONG", stop_reason="pre_trade_gate_reject")),
            ("trader_error", trader_record("LONG", stop_reason="llm_error")),
            ("trader", trader_record("WAIT", sl=None, tp=None)),
            ("trader", trader_record("LONG", stop_reason="geometry_reject")),
            ("trader", trader_record("LONG", sl=None)),
        ],
    )
    def test_trader_without_a_valid_trade_means_no_trade(
        self, case, stopped_at, trader
    ) -> None:
        assert joined(case, stopped_at, trader).final_action == "NO_TRADE"

    @pytest.mark.parametrize("side", ["LONG", "SHORT"])
    def test_valid_trader_trade_is_its_side(self, case, side) -> None:
        assert joined(case, "trader", trader_record(side)).final_action == side

    def test_bypassed_skip_is_no_trade_in_the_live_view_only(self, case) -> None:
        bypassed = joined(case, "trader", trader_record("LONG"), bypassed=True)

        assert bypassed.final_action == "LONG"
        assert bypassed.live_action == "NO_TRADE"


class TestConfusionMetrics:
    ACTUAL: ClassVar[list[str]] = [
        "LONG",
        "LONG",
        "SHORT",
        "NO_TRADE",
        "NO_TRADE",
        "NO_TRADE",
    ]
    PREDICTED: ClassVar[list[str]] = [
        "LONG",
        "NO_TRADE",
        "LONG",
        "NO_TRADE",
        "NO_TRADE",
        "SHORT",
    ]

    def test_matrix_and_per_class_rates(self) -> None:
        metrics = ConfusionMetrics(self.ACTUAL, self.PREDICTED)
        long, short, none = metrics.per_class().values()

        assert metrics.count("LONG", "NO_TRADE") == 1
        assert (long.precision, long.recall) == (0.5, 0.5)
        assert (short.precision, short.recall, short.f1) == (0.0, 0.0, 0.0)
        assert (none.precision, none.recall) == (2 / 3, 2 / 3)
        assert metrics.accuracy == 0.5
        assert metrics.macro_f1 == pytest.approx((0.5 + 0.0 + 2 / 3) / 3)

    def test_trade_precision_counts_only_traded_cases(self) -> None:
        metrics = ConfusionMetrics(self.ACTUAL, self.PREDICTED)

        assert (metrics.trade_hits, metrics.trades) == (1, 3)
        assert metrics.trade_precision == pytest.approx(1 / 3)

    def test_zero_denominators_are_none(self) -> None:
        metrics = ConfusionMetrics(["LONG", "LONG"], ["NO_TRADE", "NO_TRADE"])
        long, short, _ = metrics.per_class().values()

        assert long.precision is None
        assert long.recall == 0.0
        assert short.recall is None
        assert short.f1 is None
        assert metrics.trade_precision is None

    def test_empty_input_has_no_accuracy_or_macro_f1(self) -> None:
        metrics = ConfusionMetrics([], [])

        assert metrics.accuracy is None
        assert metrics.macro_f1 is None

    def test_unknown_class_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown classes"):
            ConfusionMetrics(["LONG"], ["WAIT"])

    def test_live_view_penalises_bypassed_trades(self, case) -> None:
        trade = joined(case, "trader", trader_record("LONG"), bypassed=True)
        labels = [trade.case.label.value]

        bot = ConfusionMetrics(labels, [trade.final_action])
        live = ConfusionMetrics(labels, [trade.live_action])

        assert bot.trade_precision == 1.0
        assert live.trade_precision is None
        assert (bot.accuracy, live.accuracy) == (1.0, 0.0)


def _metrics(
    latency_ms: float,
    cost: float | None,
    requests: int = 1,
    error: str | None = None,
    *,
    refusal: bool = False,
) -> StageMetricsSchema:
    usage = TokenUsageSchema(
        input_tokens=100, output_tokens=10, cache_read_tokens=60, cache_write_tokens=5
    )
    return StageMetricsSchema(
        requests=requests,
        latency_ms=latency_ms,
        cost_usd=cost,
        usage=usage,
        error=error,
        refusal=refusal,
    )


class TestStageOps:
    def test_latency_percentiles_and_max(self) -> None:
        ops = StageOps([_metrics(ms, 0.1) for ms in (100, 200, 300, 400)])

        assert ops.latency_ms(50) == 250
        assert ops.latency_ms(95) == pytest.approx(385)
        assert ops.max_latency_ms == 400

    def test_stages_that_never_ran_are_ignored_and_empty_is_none(self) -> None:
        ops = StageOps([StageMetricsSchema()])

        assert ops.cases == 0
        assert ops.latency_ms(50) is None
        assert ops.max_latency_ms is None

    def test_cost_tokens_and_retries_are_summed(self) -> None:
        ops = StageOps(
            [_metrics(1, 0.25), _metrics(1, 0.5, requests=3), _metrics(1, None)]
        )

        assert ops.cost_usd == 0.75
        assert ops.unpriced == 1
        assert ops.retries == 2
        assert (ops.input_tokens, ops.output_tokens) == (300, 30)
        assert (ops.cache_read_tokens, ops.cache_write_tokens) == (180, 15)

    def test_failures_are_told_apart(self) -> None:
        ops = StageOps(
            [
                _metrics(1, 0.1, error="refusal", refusal=True),
                _metrics(1, 0.1, error="no_decision"),
                _metrics(1, 0.1, error="ContentFilterError"),
                _metrics(1, 0.1),
            ]
        )

        assert (ops.refusals, ops.parse_failures, ops.api_errors) == (1, 1, 1)
