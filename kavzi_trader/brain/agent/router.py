import logging
import time

from kavzi_trader.brain.agent.analyst_pipeline import AnalystPipeline
from kavzi_trader.brain.agent.circuit_breaker import AgentCircuitBreaker
from kavzi_trader.brain.agent.decision_dedup import (
    DecisionDeduplicator,
)
from kavzi_trader.brain.agent.llm_error_logging import log_llm_exception
from kavzi_trader.brain.agent.protocols import (
    AnalystRunner,
    ConfluenceOverrideProvider,
    DependenciesProvider,
    ScoutRunner,
    TraderRunner,
)
from kavzi_trader.brain.agent.router_config import RouterConfigSchema
from kavzi_trader.brain.agent.scout_pipeline import ScoutPipeline
from kavzi_trader.brain.agent.trader_pipeline import TraderPipeline
from kavzi_trader.brain.geometry.calculator import TradeGeometryCalculator
from kavzi_trader.brain.geometry.schemas import TradeGeometrySchema
from kavzi_trader.brain.schemas.dependencies import (
    TradingDependenciesSchema,
)
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema

logger = logging.getLogger(__name__)


class PipelineResult:
    __slots__ = (
        "analyst",
        "geometry",
        "regime_gate",
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
        regime_gate: int | None = None,
    ) -> None:
        self.scout = scout
        self.analyst = analyst
        self.trader = trader
        self.trader_deps = trader_deps
        self.geometry = geometry
        self.trader_stop_reason = trader_stop_reason
        # Signal-scaled regime gate from the Analyst stage; set whenever an
        # Analyst decision is, so downstream gates never recompute it.
        if analyst is not None and regime_gate is None:
            msg = "regime_gate is required when an Analyst decision is present"
            raise ValueError(msg)
        self.regime_gate = regime_gate


# Minimum algorithm confluence to escalate to the Analyst LLM. The Analyst
# can add at most +3 points to the final confluence_score, so threshold is
# (CONFLUENCE_ENTER_MIN - 3) = 3 with all 8 signals — below this, even a
# perfect LLM bonus cannot reach the entry gate. Lowered when fewer signals
# are available (see effective_min_algo_confluence).
_DEFAULT_ANALYST_MIN_ALGO_CONFLUENCE = 3

# Number of consecutive Trader validation failures (UnexpectedModelBehavior
# or malformed output rejected downstream) before the Trader is suspended
# for a symbol. Resets on a successful Trader decision.
_DEFAULT_TRADER_CIRCUIT_THRESHOLD = 3

# Default ceiling for concurrent Analyst LLM calls from a single
# ReasoningLoop cycle. Mirrors the BrainConfigSchema default so tests and
# callers that omit the argument stay consistent with production.
_DEFAULT_ANALYST_CONCURRENCY_LIMIT = 3


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
        return self._trader_pipeline.record_validation_failure(symbol)

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
        log_llm_exception(
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
                regime_gate=analyst_result.regime_gate,
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
            return PipelineResult(
                scout=scout_result,
                analyst=analyst_decision,
                regime_gate=analyst_result.regime_gate,
            )

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
            regime_gate=analyst_result.regime_gate,
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
