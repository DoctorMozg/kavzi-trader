import logging
import time
from typing import Protocol

from pydantic_ai.exceptions import (
    ModelHTTPError,
    ModelRateLimitError,
    UnexpectedModelBehavior,
)

from kavzi_trader.brain.agent.analyst_pipeline import AnalystPipeline
from kavzi_trader.brain.agent.circuit_breaker import AgentCircuitBreaker
from kavzi_trader.brain.agent.decision_dedup import (
    DecisionDeduplicator,
)
from kavzi_trader.brain.agent.llm_errors import LLM_TIMEOUT_ERRORS
from kavzi_trader.brain.agent.router_config import RouterConfigSchema
from kavzi_trader.brain.agent.scout_pipeline import ScoutPipeline
from kavzi_trader.brain.agent.trader_pipeline import TraderPipeline
from kavzi_trader.brain.geometry.calculator import TradeGeometryCalculator
from kavzi_trader.brain.geometry.schemas import TradeGeometrySchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.scout_dependencies import ScoutDependenciesSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema

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
    def get_confluence_override(self, direction: str) -> int | None: ...


class DependenciesProvider(Protocol):
    def indicators_available(self, symbol: str) -> bool: ...

    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema: ...

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema: ...

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema: ...

    def clear_cycle_cache(self) -> None: ...


class PipelineResult:
    __slots__ = (
        "analyst",
        "geometry",
        "scout",
        "trader",
        "trader_deps",
        "trader_stop_reason",
    )

    def __init__(
        self,
        scout: ScoutDecisionSchema,
        analyst: AnalystDecisionSchema | None = None,
        trader: TradeDecisionSchema | None = None,
        trader_deps: TradingDependenciesSchema | None = None,
        geometry: TradeGeometrySchema | None = None,
        trader_stop_reason: str | None = None,
    ) -> None:
        self.scout = scout
        self.analyst = analyst
        self.trader = trader
        self.trader_deps = trader_deps
        self.geometry = geometry
        self.trader_stop_reason = trader_stop_reason


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
    if isinstance(exc, ModelRateLimitError):
        extra = base_extra | {"http_status": 429, "retry_after": exc.retry_after}
        logger.warning(
            "%s LLM rate-limited for %s after %.1fms (retry_after=%s): %s",
            agent,
            symbol,
            elapsed_ms,
            exc.retry_after,
            str(exc)[:exc_message_preview_chars],
            extra=extra,
        )
        return
    if isinstance(exc, ModelHTTPError):
        extra = base_extra | {
            "http_status": exc.status_code,
            "retry_after": exc.retry_after,
        }
        logger.warning(
            "%s LLM HTTP %s for %s after %.1fms (retry_after=%s): %s",
            agent,
            exc.status_code,
            symbol,
            elapsed_ms,
            exc.retry_after,
            str(exc)[:exc_message_preview_chars],
            extra=extra,
        )
        return
    if isinstance(exc, LLM_TIMEOUT_ERRORS):
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
    logger.error(
        "%s LLM failed for %s after %.1fms (type=%s): %s",
        agent,
        symbol,
        elapsed_ms,
        type(exc).__name__,
        str(exc)[:exc_message_preview_chars],
        exc_info=exc,
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
        geometry_calculator: TradeGeometryCalculator | None = None,
        router_config: RouterConfigSchema | None = None,
    ) -> None:
        self._scout = scout
        self._analyst = analyst
        self._trader = trader
        self._circuit_breaker = AgentCircuitBreaker(
            threshold=trader_circuit_threshold,
        )
        self._router_config = router_config or RouterConfigSchema()
        # Geometry computation is an injected collaborator. When omitted it
        # defaults to one built from the default risk config; production
        # injects app_config.risk so the calculator honours configured
        # leverage and stop bounds.
        self._geometry = geometry_calculator or TradeGeometryCalculator(
            RiskConfigSchema()
        )
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
        # (breakout %B, geometry viability), LLM invocation with timeout /
        # UnexpectedModelBehavior / generic-exception fallbacks, the
        # geometry-derivation step, and the post-success cache +
        # failure-counter reset.
        self._trader_pipeline = TraderPipeline(
            trader=self._trader,
            dedup=self._dedup,
            circuit_breaker=self._circuit_breaker,
            router_config=self._router_config,
            log_llm_exception=self._log_llm_exception,
            geometry=self._geometry,
        )

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
            geometry=trader_run.geometry,
            trader_stop_reason=trader_run.reason,
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
