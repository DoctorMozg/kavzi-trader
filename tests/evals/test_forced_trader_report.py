from pathlib import Path

import pytest

from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.joined_case_schema import JoinedCaseSchema
from kavzi_trader.evals.loaded_run_schema import LoadedRunSchema
from kavzi_trader.evals.run_header_schema import RunHeaderSchema
from kavzi_trader.evals.run_report_builder import RunReportBuilder
from kavzi_trader.evals.stage_metrics_schema import StageMetricsSchema
from tests.evals.eval_fixtures import write_cache
from tests.evals.report_fixtures import (
    DECISION,
    case_for,
    flat_frame,
    joined,
    trader_record,
)

FORCED_TITLE = "## Trader on forced cases"
LIVE_BOT_ROW = "| bot (Trader's own entry/SL/TP) | 1 |"


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    frame = flat_frame()
    frame.loc[DECISION + 1, "high"] = 105.0  # a LONG with TP 104 is hit next bar
    write_cache(tmp_path, frame)
    return tmp_path


def _case(label: str, case_id: str) -> EvalCaseSchema:
    return case_for(flat_frame(), label, case_id=case_id)


def _run(scored: list[JoinedCaseSchema], *, force_trader: bool) -> LoadedRunSchema:
    header = RunHeaderSchema(
        run_id="run_test",
        dataset="cases.jsonl",
        analyst_model="a",
        analyst_effort="low",
        trader_model="t",
        trader_effort="low",
        provider="anthropic",
        bypass_scout=False,
        force_trader=force_trader,
        concurrency=1,
    )
    return LoadedRunSchema(
        header=header, results=[j.result for j in scored], scored=scored
    )


def _organic() -> JoinedCaseSchema:
    metrics = StageMetricsSchema(requests=1, cost_usd=0.5)
    return joined(
        _case("LONG", "organic"), "trader", trader_record("LONG", metrics=metrics)
    )


def _forced(label: str, case_id: str, action: str, cost: float) -> JoinedCaseSchema:
    record = trader_record(
        action, metrics=StageMetricsSchema(requests=1, cost_usd=cost)
    )
    return joined(_case(label, case_id), "analyst_gate", record, forced=True)


def _forced_cases() -> list[JoinedCaseSchema]:
    return [
        _forced("LONG", "forced-long", "LONG", 0.25),
        _forced("SHORT", "forced-short", "LONG", 0.25),
        _forced("NO_TRADE", "forced-quiet", "WAIT", 0.25),
    ]


class TestForcedSection:
    def test_report_without_forced_cases_has_no_forced_section(
        self, cache_dir: Path
    ) -> None:
        markdown = RunReportBuilder(
            _run([_organic()], force_trader=False), cache_dir
        ).markdown()

        assert FORCED_TITLE not in markdown

    def test_forced_section_shows_actions_agreement_and_baselines(
        self, cache_dir: Path
    ) -> None:
        scored = [_organic(), *_forced_cases()]

        markdown = RunReportBuilder(
            _run(scored, force_trader=True), cache_dir
        ).markdown()

        section = markdown.split(FORCED_TITLE)[1].split("\n## ")[0]
        assert "3 cases stopped at the Analyst gate" in section
        assert "| label | n | LONG | WAIT |" in section
        assert "| NO_TRADE | 1 | 0 | 1 |" in section
        assert "| LONG | 1 | 1 | 100.0% (1/1) |" in section
        assert "| SHORT | 1 | 1 | 0.0% (0/1) |" in section
        # The forced LONG on the SHORT-labelled case is the second trade.
        assert "| Trader (forced cases) | 2 |" in section
        for baseline in ("oracle", "always long", "always short", "random side"):
            assert f"| {baseline}" in section

    def test_forced_trades_stay_out_of_the_live_matrix_and_live_r(
        self, cache_dir: Path
    ) -> None:
        scored = [_organic(), *_forced_cases()]

        markdown = RunReportBuilder(
            _run(scored, force_trader=True), cache_dir
        ).markdown()

        decisions = markdown.split("## Final decision vs label")[1].split("\n## ")[0]
        assert "| LONG | 1 | 0 | 1 |" in decisions  # forced LONG still NO_TRADE
        assert "| SHORT | 0 | 0 | 1 |" in decisions
        assert LIVE_BOT_ROW in markdown.split("## Simulated outcome")[1]

    def test_ops_include_forced_trader_cost(self, cache_dir: Path) -> None:
        scored = [_organic(), *_forced_cases()]

        markdown = RunReportBuilder(
            _run(scored, force_trader=True), cache_dir
        ).markdown()

        assert "| trader | 4 |" in markdown  # organic + three forced requests
        assert "Total $1.2500" in markdown

    def test_header_shows_the_flag(self, cache_dir: Path) -> None:
        markdown = RunReportBuilder(
            _run([_organic()], force_trader=True), cache_dir
        ).markdown()

        assert "| Force trader | True |" in markdown
