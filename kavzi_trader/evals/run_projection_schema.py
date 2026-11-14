from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.case_result_schema import CaseResultSchema


class RunProjectionSchema(BaseModel):
    """Dry-run cost and latency per case, extrapolated to the remaining cases."""

    measured_cases: Annotated[int, Field(..., ge=0)]
    mean_cost_usd: Annotated[float, Field(..., ge=0)]
    max_cost_usd: Annotated[float, Field(..., ge=0)]
    mean_latency_s: Annotated[float, Field(..., ge=0)]
    max_latency_s: Annotated[float, Field(..., ge=0)]
    remaining_cases: Annotated[int, Field(..., ge=0)]
    projected_cost_usd: Annotated[float, Field(..., ge=0)]
    projected_time_s: Annotated[float, Field(..., ge=0)]

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_results(
        cls, results: list[CaseResultSchema], remaining: int, concurrency: int
    ) -> RunProjectionSchema:
        costs = [_cost_usd(r) for r in results]
        latencies_s = [_latency_s(r) for r in results]
        count = max(len(results), 1)
        mean_latency = sum(latencies_s) / count
        mean_cost = sum(costs) / count
        return cls(
            measured_cases=len(results),
            mean_cost_usd=mean_cost,
            max_cost_usd=max(costs, default=0.0),
            mean_latency_s=mean_latency,
            max_latency_s=max(latencies_s, default=0.0),
            remaining_cases=remaining,
            projected_cost_usd=mean_cost * remaining,
            projected_time_s=mean_latency * remaining / max(concurrency, 1),
        )


def _cost_usd(result: CaseResultSchema) -> float:
    stages = [s.metrics for s in (result.analyst, result.trader) if s is not None]
    return sum(m.cost_usd or 0.0 for m in stages)


def _latency_s(result: CaseResultSchema) -> float:
    stages = [s.metrics for s in (result.analyst, result.trader) if s is not None]
    return sum(m.latency_ms for m in stages) / 1000
