import asyncio
import logging
import time
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.brain.agent.decision_dedup import DecisionDeduplicator
from kavzi_trader.brain.schemas.analyst import (
    AnalystDecisionSchema,
    KeyLevelsSchema,
)
from kavzi_trader.brain.schemas.dependencies import AnalystDependenciesSchema
from kavzi_trader.orchestrator.loops.confluence_thresholds import (
    CONFLUENCE_ENTER_MIN,
    confluence_enter_min_for_regime,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime

logger = logging.getLogger(__name__)

# Minimum Analyst confluence_score required to escalate to the Trader tier.
# Sourced from the shared confluence_thresholds module so reasoning loop,
# router, and prompt templates all use the same value.
_ANALYST_CONFLUENCE_ENTER = CONFLUENCE_ENTER_MIN


class AnalystRunner(Protocol):
    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema: ...


class AnalystDepsFetcher(Protocol):
    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema: ...


class ConfluenceOverrideProvider(Protocol):
    def get_confluence_override(self) -> int | None: ...


class LLMExceptionLogger(Protocol):
    def __call__(
        self,
        symbol: str,
        agent: str,
        exc: BaseException,
        elapsed_ms: float,
    ) -> None: ...


_AnalystStopReason = Literal[
    "no_candles",
    "agent_error",
    "below_min_algo_confluence",
    "invalid_or_below_gate",
    "ok",
]


class AnalystPipelineResultSchema(BaseModel):
    """Outcome of the Analyst pipeline stage.

    Carries everything ``AgentRouter.run`` needs to decide whether to stop
    the pipeline or escalate to the Trader tier. ``stop`` is True when:

    * Analyst deps have no candles (transient data gap, no cache write).
    * Max algorithm confluence is below ``min_algo_confluence`` (synthetic
      invalid decision carried in ``decision``).
    * The Analyst LLM raised an exception (``decision`` is None).
    * The Analyst verdict is invalid or its ``confluence_score`` is below
      the regime-specific escalation gate (possibly tightened by the
      ``ConfluenceOverrideProvider``).

    ``cached`` is True only when the verdict was served from the dedup
    cache without re-invoking the Analyst LLM.
    """

    decision: Annotated[AnalystDecisionSchema | None, Field(default=None)]
    regime: Annotated[VolatilityRegime, Field(...)]
    stop: Annotated[bool, Field(...)]
    cached: Annotated[bool, Field(default=False)]
    reason: Annotated[_AnalystStopReason, Field(...)]

    model_config = ConfigDict(frozen=True)


class AnalystPipeline:
    """Orchestrates the Analyst stage: dedup, guarded invoke, confluence gate.

    Extracted from ``AgentRouter`` so the router's ``run`` method can
    delegate Analyst orchestration in one call and concentrate on Scout
    stop-conditions and Trader escalation. Preserves the original behaviour
    exactly — including log messages, synthetic-invalid sentinel, dedup
    semantics, semaphore-guarded LLM calls, and the regime-aware
    confluence gate with its optional override.
    """

    def __init__(
        self,
        analyst: AnalystRunner,
        dedup: DecisionDeduplicator,
        min_algo_confluence: int,
        concurrency_limit: int,
        confluence_override: ConfluenceOverrideProvider | None,
        log_llm_exception: LLMExceptionLogger,
    ) -> None:
        self._analyst = analyst
        self._dedup = dedup
        self._min_algo_confluence = min_algo_confluence
        self._concurrency_limit = concurrency_limit
        self._confluence_override = confluence_override
        self._log_llm_exception = log_llm_exception
        # Semaphore gating Analyst LLM calls. Acquired only around the LLM
        # await so cached dedup hits and deterministic skip gates don't
        # consume slots. Created lazily per event loop so construction in
        # tests without a running loop stays cheap.
        self._semaphore: asyncio.Semaphore | None = None

    async def run(
        self,
        symbol: str,
        deps_provider: AnalystDepsFetcher,
    ) -> AnalystPipelineResultSchema:
        """Execute the Analyst stage for ``symbol``.

        * Fetches Analyst dependencies via the provider.
        * Short-circuits on empty candles (no cache).
        * Emits a synthetic invalid decision when the algorithm confluence
          is too low to ever pass the entry gate.
        * Consults the dedup cache keyed on (symbol, bar_close).
        * Otherwise invokes the Analyst under the concurrency semaphore;
          caches only successful runs.
        * Applies the regime-aware confluence gate (optionally tightened
          by the configured override provider).
        """
        deps = await deps_provider.get_analyst(symbol)
        self._log_analyst_inputs(deps)
        regime = deps.volatility_regime

        # Gate: skip the LLM call when algorithm confluence is too low.
        # The Analyst can add at most +3 points; if max algo < threshold,
        # even the maximum boost cannot reach the confluence entry gate.
        conf = deps.algorithm_confluence
        max_algo = max(conf.long.score, conf.short.score)
        if max_algo < self._min_algo_confluence:
            logger.info(
                "Analyst skipped for %s: max algorithm confluence %d < %d"
                " — insufficient for valid setup even with LLM bonus",
                symbol,
                max_algo,
                self._min_algo_confluence,
            )
            synthetic = AnalystDecisionSchema(
                setup_valid=False,
                direction="NEUTRAL",
                confluence_score=max_algo,
                key_levels=KeyLevelsSchema(levels=[]),
                reasoning=(
                    f"Analyst LLM call skipped: maximum algorithm"
                    f" confluence score {max_algo}/8 is below the"
                    f" minimum threshold"
                    f" {self._min_algo_confluence}. Even with"
                    f" the maximum analyst bonus of +3, the total cannot"
                    f" reach the confluence entry gate"
                    f" ({_ANALYST_CONFLUENCE_ENTER}) required to run"
                    f" the Trader tier."
                ),
            )
            return AnalystPipelineResultSchema(
                decision=synthetic,
                regime=regime,
                stop=True,
                cached=False,
                reason="below_min_algo_confluence",
            )

        if not deps.recent_candles:
            logger.warning(
                "Analyst deps for %s have no candles; returning None", symbol
            )
            return AnalystPipelineResultSchema(
                decision=None,
                regime=regime,
                stop=True,
                cached=False,
                reason="no_candles",
            )

        # Bar-close dedup: if the latest closed candle hasn't changed since
        # the previous Analyst call for this symbol, reuse the memoized
        # result. Skips redundant LLM calls inside the same 5-minute bar
        # when the ReasoningLoop cooldown expires mid-bar.
        current_bar = deps.recent_candles[-1].close_time
        cached = self._dedup.analyst_hit(symbol, current_bar)
        if cached is not None:
            logger.info(
                "Analyst dedup hit for %s: bar close_time=%s already"
                " analyzed (cached conf=%d, valid=%s)",
                symbol,
                current_bar,
                cached.confluence_score,
                cached.setup_valid,
            )
            return self._apply_confluence_gate(
                symbol,
                decision=cached,
                regime=regime,
                cached=True,
            )

        t0 = time.monotonic()
        try:
            async with self._get_semaphore():
                result = await self._analyst.run(deps)
        except Exception as exc:  # noqa: BLE001 - LLM client raises many types
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._log_llm_exception(symbol, "analyst", exc, elapsed_ms)
            return AnalystPipelineResultSchema(
                decision=None,
                regime=regime,
                stop=True,
                cached=False,
                reason="agent_error",
            )

        # Record the bar we just analyzed so subsequent cycles within the
        # same candle can short-circuit via the dedup hit above.
        self._dedup.cache_analyst(symbol, bar_close=current_bar, result=result)
        return self._apply_confluence_gate(
            symbol,
            decision=result,
            regime=regime,
            cached=False,
        )

    def _apply_confluence_gate(
        self,
        symbol: str,
        *,
        decision: AnalystDecisionSchema,
        regime: VolatilityRegime,
        cached: bool,
    ) -> AnalystPipelineResultSchema:
        """Apply the regime-specific escalation gate + optional override.

        Replaces the prior flat ``CONFLUENCE_ENTER_MIN`` with
        NORMAL=6, HIGH=7, EXTREME=8, LOW=7 so volatile markets can still
        trade on genuinely strong setups. The confluence override (e.g.
        elevated-fear FGI gate) can tighten the gate further but never
        loosen it.
        """
        confluence_gate = confluence_enter_min_for_regime(regime)
        if self._confluence_override is not None:
            override = self._confluence_override.get_confluence_override()
            if override is not None:
                confluence_gate = max(confluence_gate, override)

        passed = decision.confluence_score >= confluence_gate
        logger.info(
            "Analyst regime gate for %s: score=%d gate=%d regime=%s pass=%s",
            symbol,
            decision.confluence_score,
            confluence_gate,
            regime.value,
            passed,
            extra={
                "symbol": symbol,
                "agent": "analyst",
                "confluence_score": decision.confluence_score,
                "confluence_gate": confluence_gate,
                "volatility_regime": regime.value,
            },
        )

        if not decision.setup_valid or not passed:
            return AnalystPipelineResultSchema(
                decision=decision,
                regime=regime,
                stop=True,
                cached=cached,
                reason="invalid_or_below_gate",
            )
        return AnalystPipelineResultSchema(
            decision=decision,
            regime=regime,
            stop=False,
            cached=cached,
            reason="ok",
        )

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazily materialize the Analyst semaphore on the running event loop.

        Creating it in ``__init__`` would bind it to whichever loop happens
        to be current at construction time, which fails in tests that
        construct the pipeline outside the loop they later drive.
        """
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._concurrency_limit)
        return self._semaphore

    @staticmethod
    def _log_analyst_inputs(deps: AnalystDependenciesSchema) -> None:
        ind = deps.indicators
        of = deps.order_flow
        conf = deps.algorithm_confluence
        logger.info(
            "Analyst inputs %s: price=%s regime=%s RSI=%s "
            "MACD=%s BB%%b=%s vol=%s funding=%s OI_1h=%s "
            "L/S=%s conf=%s/%s(%s) sent=%s '%s'",
            deps.symbol,
            deps.current_price,
            deps.volatility_regime.value,
            ind.rsi_14,
            ind.macd.histogram if ind.macd else None,
            ind.bollinger.percent_b if ind.bollinger else None,
            ind.volume.volume_ratio if ind.volume else None,
            of.funding_rate if of else None,
            of.oi_change_1h_percent if of else None,
            of.long_short_ratio if of else None,
            conf.long.score,
            conf.short.score,
            conf.detected_side,
            deps.sentiment_summary.sentiment_bias if deps.sentiment_summary else None,
            deps.sentiment_summary.summary[:30] if deps.sentiment_summary else "",
        )
