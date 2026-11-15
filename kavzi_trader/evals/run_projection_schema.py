from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.case_result_schema import CaseResultSchema


class RunProjectionSchema(BaseModel):
    """Dry-run cost and latency per LLM case, extrapolated to the remaining cases.

    Only measured cases that reached the Analyst LLM count towards the means: the
    others stopped at a free gate. ``reach_fraction`` is the share of the remaining
    cases the deterministic pre-pass expects to reach the LLM.
    """

    measured_cases: Annotated[int, Field(..., ge=0)]
    llm_cases: Annotated[int, Field(..., ge=0)]
    mean_cost_usd: Annotated[float, Field(..., ge=0)]
    max_cost_usd: Annotated[float, Field(..., ge=0)]
    mean_latency_s: Annotated[float, Field(..., ge=0)]
    max_latency_s: Annotated[float, Field(..., ge=0)]
    remaining_cases: Annotated[int, Field(..., ge=0)]
    reach_fraction: Annotated[float, Field(..., ge=0, le=1)]
    projected_cost_usd: Annotated[float, Field(..., ge=0)]
    projected_time_s: Annotated[float, Field(..., ge=0)]

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_results(
        cls,
        results: list[CaseResultSchema],
        remaining: int,
        concurrency: int,
        reach_fraction: float,
    ) -> RunProjectionSchema:
        llm_results = [r for r in results if _reached_llm(r)]
        costs = [_cost_usd(r) for r in llm_results]
        latencies_s = [_latency_s(r) for r in llm_results]
        count = max(len(llm_results), 1)
        mean_latency = sum(latencies_s) / count
        mean_cost = sum(costs) / count
        expected_llm_cases = remaining * reach_fraction
        return cls(
            measured_cases=len(results),
            llm_cases=len(llm_results),
            mean_cost_usd=mean_cost,
            max_cost_usd=max(costs, default=0.0),
            mean_latency_s=mean_latency,
            max_latency_s=max(latencies_s, default=0.0),
            remaining_cases=remaining,
            reach_fraction=reach_fraction,
            projected_cost_usd=mean_cost * expected_llm_cases,
            projected_time_s=mean_latency * expected_llm_cases / max(concurrency, 1),
        )


def _reached_llm(result: CaseResultSchema) -> bool:
    return result.analyst is not None and result.analyst.metrics.requests > 0


def _cost_usd(result: CaseResultSchema) -> float:
    stages = [s.metrics for s in (result.analyst, result.trader) if s is not None]
    return sum(m.cost_usd or 0.0 for m in stages)


def _latency_s(result: CaseResultSchema) -> float:
    stages = [s.metrics for s in (result.analyst, result.trader) if s is not None]
    return sum(m.latency_ms for m in stages) / 1000
