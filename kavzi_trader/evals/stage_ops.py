import numpy as np

from kavzi_trader.evals.stage_metrics_schema import StageMetricsSchema

_NON_API = {"no_decision", "refusal"}


class StageOps:
    """Latency, cost, tokens and failures of one LLM stage."""

    def __init__(self, metrics: list[StageMetricsSchema]) -> None:
        self._all = [m for m in metrics if m.requests > 0]

    @property
    def cases(self) -> int:
        return len(self._all)

    @property
    def requests(self) -> int:
        return sum(m.requests for m in self._all)

    @property
    def retries(self) -> int:
        return self.requests - self.cases

    def latency_ms(self, percentile: float) -> float | None:
        if not self._all:
            return None
        return float(np.percentile([m.latency_ms for m in self._all], percentile))

    @property
    def max_latency_ms(self) -> float | None:
        return max((m.latency_ms for m in self._all), default=None)

    @property
    def cost_usd(self) -> float:
        return sum(m.cost_usd or 0.0 for m in self._all)

    @property
    def unpriced(self) -> int:
        return sum(m.cost_usd is None for m in self._all)

    @property
    def input_tokens(self) -> int:
        return sum(m.usage.input_tokens for m in self._all)

    @property
    def output_tokens(self) -> int:
        return sum(m.usage.output_tokens for m in self._all)

    @property
    def cache_read_tokens(self) -> int:
        return sum(m.usage.cache_read_tokens for m in self._all)

    @property
    def cache_write_tokens(self) -> int:
        return sum(m.usage.cache_write_tokens for m in self._all)

    @property
    def refusals(self) -> int:
        return sum(m.refusal for m in self._all)

    @property
    def parse_failures(self) -> int:
        return sum(m.error == "no_decision" for m in self._all)

    @property
    def api_errors(self) -> int:
        return sum(m.error is not None and m.error not in _NON_API for m in self._all)

    @property
    def total_latency_ms(self) -> float:
        return sum(m.latency_ms for m in self._all)
