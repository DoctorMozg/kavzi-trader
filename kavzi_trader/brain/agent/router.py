import logging
import time
from decimal import Decimal
from typing import Protocol

import httpx
import openai
from pydantic_ai.exceptions import UnexpectedModelBehavior

from kavzi_trader.brain.agent.analyst_pipeline import AnalystPipeline
from kavzi_trader.brain.agent.circuit_breaker import AgentCircuitBreaker
from kavzi_trader.brain.agent.decision_dedup import (
    AnalystDedupEntry,
    DecisionDeduplicator,
    ScoutDedupEntry,
    TraderDedupEntry,
)
from kavzi_trader.brain.agent.router_config import RouterConfigSchema
from kavzi_trader.brain.agent.scout_pipeline import ScoutPipeline
from kavzi_trader.brain.agent.trader_pipeline import TraderPipeline
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema

logger = logging.getLogger(__name__)


class ScoutRunner(Protocol):
    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema: ...


class AnalystRunner(Protocol):
    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema: ...


class TraderRunner(Protocol):
    async def run(
        self,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema | None = None,
        scout_pattern: str | None = None,
    ) -> TradeDecisionSchema: ...


class ConfluenceOverrideProvider(Protocol):
    def get_confluence_override(self) -> int | None: ...


class DependenciesProvider(Protocol):
    def indicators_available(self, symbol: str) -> bool: ...

    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema: ...

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema: ...

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema: ...

    def clear_cycle_cache(self) -> None: ...


class PipelineResult:
    __slots__ = ("analyst", "scout", "trader", "trader_deps")

    def __init__(
        self,
        scout: ScoutDecisionSchema,
        analyst: AnalystDecisionSchema | None = None,
        trader: TradeDecisionSchema | None = None,
        trader_deps: TradingDependenciesSchema | None = None,
    ) -> None:
        self.scout = scout
        self.analyst = analyst
        self.trader = trader
        self.trader_deps = trader_deps


# Minimum algorithm confluence to escalate to the Analyst LLM. The Analyst
# can add at most +3 points to the final confluence_score, so threshold is
# (CONFLUENCE_ENTER_MIN - 3) = 3 — below this, even a perfect LLM bonus
# cannot reach the entry gate.
_DEFAULT_ANALYST_MIN_ALGO_CONFLUENCE = 3

# Number of consecutive Trader validation failures (UnexpectedModelBehavior
# or malformed output rejected downstream) before the Trader is suspended
# for a symbol. Resets on a successful Trader decision.
_DEFAULT_TRADER_CIRCUIT_THRESHOLD = 3

# Default ceiling for concurrent Analyst LLM calls from a single
# ReasoningLoop cycle. Mirrors the BrainConfigSchema default so tests and
# callers that omit the argument stay consistent with production.
_DEFAULT_ANALYST_CONCURRENCY_LIMIT = 3


def _http_status_of(exc: BaseException) -> int | None:
    """Best-effort extraction of HTTP status code from LLM / HTTP errors."""
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    status = getattr(exc, "status_code", None)
    is_status_int = isinstance(status, int)
    if is_status_int:
        return status
    return None


def _retry_after_of(exc: BaseException) -> str | None:
    """Best-effort extraction of the Retry-After header from HTTP errors."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get("retry-after")
    except AttributeError:
        return None
    if value is None:
        return None
    return str(value)


def _log_llm_exception(
    symbol: str,
    agent: str,
    exc: BaseException,
    elapsed_ms: float,
    *,
    body_preview_chars: int,
    exc_message_preview_chars: int,
) -> None:
    """Structured log dispatcher for Analyst / Trader LLM failures.

    Branches by exception type so operators can separate rate limits,
    timeouts, schema-retry exhaustion, and generic failures from the log
    stream without parsing tracebacks.
    """
    base_extra: dict[str, object] = {
        "symbol": symbol,
        "agent": agent,
        "exception_type": type(exc).__name__,
        "elapsed_ms": round(elapsed_ms, 1),
    }
    if isinstance(exc, openai.RateLimitError):
        retry_after = _retry_after_of(exc)
        extra = base_extra | {"http_status": 429, "retry_after": retry_after}
        logger.warning(
            "%s LLM rate-limited for %s after %.1fms (retry_after=%s): %s",
            agent,
            symbol,
            elapsed_ms,
            retry_after,
            str(exc)[:exc_message_preview_chars],
            extra=extra,
        )
        return
    if isinstance(exc, openai.APIStatusError):
        status = _http_status_of(exc)
        extra = base_extra | {"http_status": status}
        logger.warning(
            "%s LLM HTTP %s for %s after %.1fms: %s",
            agent,
            status,
            symbol,
            elapsed_ms,
            str(exc)[:exc_message_preview_chars],
            extra=extra,
        )
        return
    if isinstance(exc, httpx.HTTPStatusError):
        status = _http_status_of(exc)
        retry_after = _retry_after_of(exc)
        extra = base_extra | {"http_status": status, "retry_after": retry_after}
        logger.warning(
            "%s LLM HTTP %s for %s after %.1fms (retry_after=%s): %s",
            agent,
            status,
            symbol,
            elapsed_ms,
            retry_after,
            str(exc)[:exc_message_preview_chars],
            extra=extra,
        )
        return
    if isinstance(exc, httpx.TimeoutException | TimeoutError):
        logger.warning(
            "%s LLM timed out for %s after %.1fms (type=%s)",
            agent,
            symbol,
            elapsed_ms,
            type(exc).__name__,
            extra=base_extra,
        )
        return
    if isinstance(exc, UnexpectedModelBehavior):
        body_preview = str(exc.body or "")[:body_preview_chars]
        extra = base_extra | {"raw_body": exc.body, "body_preview": body_preview}
        logger.warning(
            "%s LLM unparseable output for %s after %.1fms: %s | body_preview=%s",
            agent,
            symbol,
            elapsed_ms,
            exc.message,
            body_preview,
            extra=extra,
        )
        return
    logger.exception(
        "%s LLM failed for %s after %.1fms (type=%s): %s",
        agent,
        symbol,
        elapsed_ms,
        type(exc).__name__,
        str(exc)[:exc_message_preview_chars],
        extra=base_extra,
    )


class AgentRouter:
    def __init__(
        self,
        scout: ScoutRunner,
        analyst: AnalystRunner,
        trader: TraderRunner,
        analyst_min_algo_confluence: int = _DEFAULT_ANALYST_MIN_ALGO_CONFLUENCE,
        confluence_override: ConfluenceOverrideProvider | None = None,
        trader_circuit_threshold: int = _DEFAULT_TRADER_CIRCUIT_THRESHOLD,
        analyst_concurrency_limit: int = _DEFAULT_ANALYST_CONCURRENCY_LIMIT,
        *,
        router_config: RouterConfigSchema | None = None,
    ) -> None:
        self._scout = scout
        self._analyst = analyst
        self._trader = trader
        self._circuit_breaker = AgentCircuitBreaker(
            threshold=trader_circuit_threshold,
        )
        self._router_config = router_config or RouterConfigSchema()
        # Per-symbol bar-close dedup for Scout / Analyst / Trader tiers.
        # Scout is deterministic (safe to cache INTERESTING and SKIP within
        # the same candle); Analyst is LLM-based; Trader is keyed by the
        # additional (analyst_hash, bar_close) pair so cross-bar
        # invalidation and mid-bar Analyst revisions both work.
        self._dedup = DecisionDeduplicator()
        # Scout stage orchestrator — owns fetch-deps + dedup + invoke +
        # cache for the Scout tier so ``run`` can delegate in one call.
        self._scout_pipeline = ScoutPipeline(
            scout=self._scout,
            dedup=self._dedup,
        )
        # Analyst stage orchestrator — owns the min-algo confluence skip
        # gate, bar-close dedup, semaphore-guarded LLM invocation, and the
        # regime-aware confluence entry gate (plus its optional override).
        # The semaphore is materialised lazily inside the pipeline so
        # constructing the router outside an event loop stays cheap.
        self._analyst_pipeline = AnalystPipeline(
            analyst=self._analyst,
            dedup=self._dedup,
            min_algo_confluence=analyst_min_algo_confluence,
            concurrency_limit=analyst_concurrency_limit,
            confluence_override=confluence_override,
            log_llm_exception=self._log_llm_exception,
        )
        # Trader stage orchestrator — owns the circuit-breaker short-
        # circuit, 3-tuple dedup, deterministic pre-trade gates
        # (breakout %B, R/R), LLM invocation with timeout /
        # UnexpectedModelBehavior / generic-exception fallbacks, and the
        # post-success cache + failure-counter reset.
        self._trader_pipeline = TraderPipeline(
            trader=self._trader,
            dedup=self._dedup,
            circuit_breaker=self._circuit_breaker,
            router_config=self._router_config,
            log_llm_exception=self._log_llm_exception,
        )

    @property
    def _trader_validation_failures(self) -> dict[str, int]:
        """Back-compat alias for the circuit breaker's failure map.

        Exposes the underlying dict by reference so callers that read or
        mutate raw counts (e.g. tests that assert ``== {}`` or clear the
        map) continue to see live state without a second code path.
        """
        return self._circuit_breaker.failures

    @property
    def _trader_circuit_threshold(self) -> int:
        """Back-compat alias for the circuit breaker's configured threshold."""
        return self._circuit_breaker.threshold

    @property
    def _scout_dedup(self) -> dict[str, ScoutDedupEntry]:
        """Back-compat alias for the deduplicator's Scout entry map.

        Exposes the underlying dict by reference so callers that read or
        mutate raw entries (e.g. tests that call ``.clear()`` or assert
        membership) continue to see live state without a second code path.
        """
        return self._dedup.scout_entries

    @property
    def _analyst_dedup(self) -> dict[str, AnalystDedupEntry]:
        """Back-compat alias for the deduplicator's Analyst entry map."""
        return self._dedup.analyst_entries

    @property
    def _trader_dedup(self) -> dict[str, TraderDedupEntry]:
        """Back-compat alias for the deduplicator's Trader entry map."""
        return self._dedup.trader_entries

    def record_trader_validation_failure(self, symbol: str) -> int:
        """Increment the per-symbol Trader failure counter and return the new
        count. Called by the reasoning loop when downstream schema validation
        rejects a malformed decision (e.g. missing stop_loss/take_profit);
        the Trader pipeline increments the same counter internally on
        ``UnexpectedModelBehavior``.
        """
        count = self._circuit_breaker.record_failure(symbol)
        logger.warning(
            "Trader validation failure recorded for %s (total=%d/%d)",
            symbol,
            count,
            self._circuit_breaker.threshold,
            extra={
                "symbol": symbol,
                "agent": "trader",
                "trader_validation_failures_total": count,
            },
        )
        return count

    def is_trader_circuit_open(self, symbol: str) -> bool:
        """Return True when consecutive Trader validation failures have met
        or exceeded the circuit breaker threshold for this symbol. The
        circuit resets automatically on the next successful Trader decision.
        """
        return self._circuit_breaker.is_open(symbol)

    def _log_llm_exception(
        self,
        symbol: str,
        agent: str,
        exc: BaseException,
        elapsed_ms: float,
    ) -> None:
        """Instance-scoped wrapper around the module-level log dispatcher.

        Injects the router's configured log-preview character limits so
        callers inside the class don't repeat the config plumbing.
        """
        _log_llm_exception(
            symbol,
            agent,
            exc,
            elapsed_ms,
            body_preview_chars=self._router_config.body_preview_chars,
            exc_message_preview_chars=(self._router_config.exc_message_preview_chars),
        )

    # ------------------------------------------------------------------
    # Back-compat shims: tests call the pre-trade gate and R/R estimator
    # directly on the router. The authoritative implementations now live
    # in ``TraderPipeline``; these delegators preserve the public surface
    # without a second code path.
    # ------------------------------------------------------------------

    def _pre_trader_breakout_check(
        self,
        symbol: str,
        scout_pattern: str | None,
        deps: TradingDependenciesSchema,
        *,
        analyst_direction: str,
    ) -> TradeDecisionSchema | None:
        return self._trader_pipeline.pre_trader_breakout_check(
            symbol,
            scout_pattern,
            deps,
            analyst_direction=analyst_direction,
        )

    def _pre_trader_rr_check(
        self,
        symbol: str,
        analyst_result: AnalystDecisionSchema,
        current_price: Decimal,
        atr: Decimal | None,
    ) -> TradeDecisionSchema | None:
        return self._trader_pipeline.pre_trader_rr_check(
            symbol, analyst_result, current_price, atr
        )

    _estimate_rr = staticmethod(TraderPipeline.estimate_rr)

    async def run(
        self,
        symbol: str,
        deps_provider: DependenciesProvider,
    ) -> PipelineResult:
        total_start = time.monotonic()
        logger.info("Agent pipeline started for %s", symbol)

        scout_pipeline_result = await self._scout_pipeline.run(symbol, deps_provider)
        scout_result = scout_pipeline_result.decision
        if scout_pipeline_result.stop:
            self._log_stop("Scout", symbol, total_start)
            return PipelineResult(scout=scout_result)

        analyst_result = await self._analyst_pipeline.run(symbol, deps_provider)
        analyst_decision = analyst_result.decision
        if analyst_result.stop:
            if analyst_decision is None:
                return PipelineResult(scout=scout_result)
            self._log_stop("Analyst", symbol, total_start)
            return PipelineResult(
                scout=scout_result,
                analyst=analyst_decision,
            )
        # ``stop=False`` guarantees the Analyst pipeline produced a
        # gate-passing decision; the explicit None check keeps the type
        # narrowing visible to the checker without relying on ``assert``.
        if analyst_decision is None:
            return PipelineResult(scout=scout_result)

        trader_run = await self._trader_pipeline.run(
            symbol,
            analyst_decision,
            scout_result.pattern_detected,
            deps_provider,
        )
        if trader_run.decision is None:
            return PipelineResult(scout=scout_result, analyst=analyst_decision)

        total_ms = (time.monotonic() - total_start) * 1000
        logger.info(
            "Agent pipeline completed for %s in %.1fms — reached tier trader",
            symbol,
            total_ms,
        )
        return PipelineResult(
            scout=scout_result,
            analyst=analyst_decision,
            trader=trader_run.decision,
            trader_deps=trader_run.deps,
        )

    @staticmethod
    def _log_stop(agent: str, symbol: str, start: float) -> None:
        total_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Pipeline stopped at %s for %s in %.1fms",
            agent,
            symbol,
            total_ms,
        )
