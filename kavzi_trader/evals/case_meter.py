from contextvars import ContextVar, Token
from types import TracebackType
from typing import Literal, Self

from kavzi_trader.evals.cost_calculator import CostCalculator
from kavzi_trader.evals.stage_metrics_schema import StageMetricsSchema
from kavzi_trader.evals.token_usage_schema import TokenUsageSchema

Role = Literal["analyst", "trader"]

_active: ContextVar[CaseMeter | None] = ContextVar("eval_case_meter", default=None)


class _Tally:
    def __init__(self) -> None:
        self.requests = 0
        self.latency_ms = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.error: str | None = None
        self.refusal = False


class CaseMeter:
    """Per-case tally of LLM requests and usage, filled by MeteredModel.

    Active for the duration of a ``with`` block in the task that runs the case,
    so concurrent cases never share a tally.
    """

    def __init__(self) -> None:
        self._tallies: dict[Role, _Tally] = {"analyst": _Tally(), "trader": _Tally()}
        self._token: Token[CaseMeter | None] | None = None

    @staticmethod
    def active() -> CaseMeter | None:
        return _active.get()

    def __enter__(self) -> Self:
        self._token = _active.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._token is not None:
            _active.reset(self._token)

    def record_request(
        self,
        role: Role,
        elapsed_ms: float,
        usage: TokenUsageSchema,
        *,
        refusal: bool,
    ) -> None:
        tally = self._tallies[role]
        tally.requests += 1
        tally.latency_ms += elapsed_ms
        tally.input_tokens += usage.input_tokens
        tally.output_tokens += usage.output_tokens
        tally.cache_read_tokens += usage.cache_read_tokens
        tally.cache_write_tokens += usage.cache_write_tokens
        tally.refusal = tally.refusal or refusal

    def record_failure(
        self, role: Role, elapsed_ms: float, error: BaseException
    ) -> None:
        tally = self._tallies[role]
        tally.requests += 1
        tally.latency_ms += elapsed_ms
        tally.error = f"{type(error).__name__}: {error}"[:300]

    def metrics(
        self, role: Role, model_id: str, costs: CostCalculator
    ) -> StageMetricsSchema:
        tally = self._tallies[role]
        usage = TokenUsageSchema(
            input_tokens=tally.input_tokens,
            output_tokens=tally.output_tokens,
            cache_read_tokens=tally.cache_read_tokens,
            cache_write_tokens=tally.cache_write_tokens,
        )
        return StageMetricsSchema(
            requests=tally.requests,
            latency_ms=round(tally.latency_ms, 1),
            usage=usage,
            cost_usd=costs.cost_usd(model_id, usage) if tally.requests else None,
            error=tally.error,
            refusal=tally.refusal,
        )
