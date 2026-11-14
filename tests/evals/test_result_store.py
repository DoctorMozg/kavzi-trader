from pathlib import Path

import pytest

from kavzi_trader.evals.case_result_schema import CaseResultSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.eval_run_orchestrator import EvalRunOrchestrator
from kavzi_trader.evals.result_store import ResultStore
from kavzi_trader.evals.run_header_schema import RunHeaderSchema
from tests.evals.eval_fixtures import btc_frame, case_at


def _result(case_id: str, status: str = "ok") -> CaseResultSchema:
    return CaseResultSchema.model_validate(
        {
            "case_id": case_id,
            "status": status,
            "label": "LONG",
            "regime": "NORMAL",
            "tier": "TIER_1",
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> ResultStore:
    return ResultStore(tmp_path / "evals", "run_a")


class TestResultStore:
    def test_completed_ids_skip_errors_so_they_rerun(self, store: ResultStore) -> None:
        store.append(_result("a"))
        store.append(_result("b", status="error"))

        assert store.completed_ids() == {"a"}

    def test_torn_last_line_is_ignored(self, store: ResultStore) -> None:
        store.append(_result("a"))
        with store.results_path.open("a", encoding="utf-8") as handle:
            handle.write('{"case_id": "b", "stat')

        assert store.completed_ids() == {"a"}

    def test_header_round_trips(self, store: ResultStore) -> None:
        header = RunHeaderSchema.model_validate(
            {
                "run_id": "run_a",
                "dataset": "d.jsonl",
                "analyst_model": "m1",
                "analyst_effort": "medium",
                "trader_model": "m2",
                "trader_effort": "medium",
                "provider": "anthropic",
                "bypass_scout": True,
                "concurrency": 4,
                "git_hash": "abc",
            }
        )
        store.write_header(header)

        assert store.read_header() == header

    def test_resume_without_header_fails_loudly(self, store: ResultStore) -> None:
        with pytest.raises(FileNotFoundError, match="cannot resume"):
            store.read_header()


class _ScriptedRunner:
    def __init__(self, failing: set[str] | None = None) -> None:
        self.ran: list[str] = []
        self._failing = failing or set()

    async def run_case(self, case: EvalCaseSchema) -> CaseResultSchema:
        self.ran.append(case.case_id)
        if case.case_id in self._failing:
            raise RuntimeError("boom")
        return _result(case.case_id)


class TestOrchestrator:
    @pytest.fixture
    def cases(self) -> list[EvalCaseSchema]:
        frame = btc_frame()
        return [case_at(frame, 1050 + i) for i in range(4)]

    async def test_error_is_recorded_and_the_run_continues(
        self, store: ResultStore, cases: list[EvalCaseSchema]
    ) -> None:
        runner = _ScriptedRunner(failing={cases[1].case_id})

        results = await EvalRunOrchestrator(runner, store, 2).run_batch(cases)

        assert [r.status for r in results] == ["ok", "error", "ok", "ok"]
        failed = results[1]
        assert failed.error is not None
        assert "RuntimeError: boom" in failed.error
        assert len(store.read_all()) == 4

    async def test_resume_skips_completed_cases(
        self, store: ResultStore, cases: list[EvalCaseSchema]
    ) -> None:
        first = _ScriptedRunner(failing={cases[2].case_id})
        await EvalRunOrchestrator(first, store, 4).run_batch(cases)

        done = store.completed_ids()
        pending = [c for c in cases if c.case_id not in done]
        second = _ScriptedRunner()
        await EvalRunOrchestrator(second, store, 4).run_batch(pending)

        assert second.ran == [cases[2].case_id]
        assert store.completed_ids() == {c.case_id for c in cases}

    async def test_concurrency_is_bounded(
        self, store: ResultStore, cases: list[EvalCaseSchema]
    ) -> None:
        import asyncio

        active = 0
        peak = 0

        class Slow:
            async def run_case(self, case: EvalCaseSchema) -> CaseResultSchema:
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1
                return _result(case.case_id)

        await EvalRunOrchestrator(Slow(), store, 2).run_batch(cases)

        assert peak == 2

    def test_zero_concurrency_is_rejected(self, store: ResultStore) -> None:
        with pytest.raises(ValueError, match="concurrency must be >= 1"):
            EvalRunOrchestrator(_ScriptedRunner(), store, 0)
