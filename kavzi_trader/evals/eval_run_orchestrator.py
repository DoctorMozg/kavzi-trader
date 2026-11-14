import asyncio
import logging
from typing import Protocol

from kavzi_trader.evals.case_result_schema import CaseResultSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.result_store import ResultStore

logger = logging.getLogger(__name__)


class CaseRunner(Protocol):
    async def run_case(self, case: EvalCaseSchema) -> CaseResultSchema: ...


class EvalRunOrchestrator:
    """Runs batches of cases with bounded concurrency, saving each as it ends."""

    def __init__(
        self, runner: CaseRunner, store: ResultStore, concurrency: int
    ) -> None:
        if concurrency < 1:
            msg = f"concurrency must be >= 1, got {concurrency}"
            raise ValueError(msg)
        self._runner = runner
        self._store = store
        self._semaphore = asyncio.Semaphore(concurrency)

    async def run_batch(self, cases: list[EvalCaseSchema]) -> list[CaseResultSchema]:
        return list(await asyncio.gather(*(self._run_one(c) for c in cases)))

    async def _run_one(self, case: EvalCaseSchema) -> CaseResultSchema:
        async with self._semaphore:
            try:
                result = await self._runner.run_case(case)
            except Exception as exc:
                logger.exception("Case %s failed", case.case_id)
                result = CaseResultSchema(
                    case_id=case.case_id,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}"[:500],
                    label=case.label.value,
                    regime=case.regime,
                    tier=case.tier,
                )
            self._store.append(result)
            logger.info(
                "Case %s done: status=%s stopped_at=%s",
                case.case_id,
                result.status,
                result.stopped_at,
            )
            return result
