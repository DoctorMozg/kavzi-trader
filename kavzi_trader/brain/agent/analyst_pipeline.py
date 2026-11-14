import asyncio
import logging
import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.exceptions import UnexpectedModelBehavior

from kavzi_trader.brain.agent.circuit_breaker import AgentCircuitBreaker
from kavzi_trader.brain.agent.decision_dedup import DecisionDeduplicator
from kavzi_trader.brain.agent.protocols import (
    AnalystDepsFetcher,
    AnalystRunner,
    ConfluenceOverrideProvider,
    LLMExceptionLogger,
)
from kavzi_trader.brain.confluence_thresholds import (
    COUNTER_TREND_GATE_BUMP,
    confluence_enter_min_for_regime,
    effective_min_algo_confluence,
    effective_regime_gate,
)
from kavzi_trader.brain.schemas.dependencies import AnalystDependenciesSchema
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema, KeyLevelsSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.indicators.htf import HtfTrendSchema

logger = logging.getLogger(__name__)

_AnalystStopReason = Literal[
    "no_candles",
    "agent_error",
    "circuit_open",
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
    # Regime entry gate scaled to the signals available for this evaluation.
    # Downstream cooldown/enqueue checks read it instead of recomputing.
    regime_gate: Annotated[int | None, Field(default=None)]

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
        circuit_threshold: int = 2,
        circuit_open_cycles: int = 2,
    ) -> None:
        self._analyst = analyst
        self._dedup = dedup
        self._min_algo_confluence = min_algo_confluence
        self._concurrency_limit = concurrency_limit
        self._confluence_override = confluence_override
        self._log_llm_exception = log_llm_exception
        self._circuit_breaker = AgentCircuitBreaker(
            threshold=circuit_threshold,
            cooldown_cycles=circuit_open_cycles,
        )
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
        # Circuit breaker: skip LLM while symbol is in the cooling window.
        # When the last skip cycle elapses the counter is reset so the LLM
        # is retried cleanly on the next evaluation.
        skip_remaining = self._circuit_breaker.consume_cooldown_cycle(symbol)
        if skip_remaining > 0:
            logger.warning(
                "Analyst circuit open for %s: skipping LLM call (%d cycles remaining)",
                symbol,
                skip_remaining,
                extra={"symbol": symbol, "agent": "analyst"},
            )
            return AnalystPipelineResultSchema(
                decision=None,
                regime=VolatilityRegime.NORMAL,
                stop=True,
                cached=False,
                reason="circuit_open",
                regime_gate=None,
            )

        deps = await deps_provider.get_analyst(symbol)
        self._log_analyst_inputs(deps)
        regime = deps.volatility_regime
        available = deps.algorithm_confluence.dominant.available_signals
        regime_gate = effective_regime_gate(regime, available)
        min_algo = effective_min_algo_confluence(self._min_algo_confluence, available)
        self._log_scaled_gates(
            symbol, regime, available, regime_gate, min_algo=min_algo
        )

        # Gate: skip the LLM call when algorithm confluence is too low.
        # The Analyst can add at most +3 points; if max algo < threshold,
        # even the maximum boost cannot reach the confluence entry gate.
        conf = deps.algorithm_confluence
        max_algo = max(conf.long.score, conf.short.score)
        if max_algo < min_algo:
            dominant_side = "LONG" if conf.long.score >= conf.short.score else "SHORT"
            logger.info(
                "Analyst skipped for %s: max algorithm confluence %d < %d"
                " — insufficient for valid setup even with LLM bonus",
                symbol,
                max_algo,
                min_algo,
                extra={
                    "symbol": symbol,
                    "agent": "analyst",
                    "long_confluence": conf.long.score,
                    "short_confluence": conf.short.score,
                    "dominant_confluence_side": dominant_side,
                },
            )
            synthetic = AnalystDecisionSchema(
                setup_valid=False,
                direction="NEUTRAL",
                confluence_score=max_algo,
                key_levels=KeyLevelsSchema(levels=[]),
                reasoning=(
                    f"Analyst LLM call skipped: maximum algorithm"
                    f" confluence score {max_algo}/{available} is below the"
                    f" minimum threshold"
                    f" {min_algo}. Even with"
                    f" the maximum analyst bonus of +3, the total cannot"
                    f" reach the confluence entry gate"
                    f" ({regime_gate}) required to run"
                    f" the Trader tier."
                ),
            )
            return AnalystPipelineResultSchema(
                decision=synthetic,
                regime=regime,
                stop=True,
                cached=False,
                reason="below_min_algo_confluence",
                regime_gate=regime_gate,
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
                regime_gate=regime_gate,
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
                htf_trend=deps.htf_trend,
                regime_gate=regime_gate,
                cached=True,
            )

        t0 = time.monotonic()
        try:
            async with self._get_semaphore():
                result = await self._analyst.run(deps)
        except Exception as exc:  # noqa: BLE001 - LLM client raises many types
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._log_llm_exception(symbol, "analyst", exc, elapsed_ms)
            if isinstance(exc, UnexpectedModelBehavior):
                failures = self._circuit_breaker.record_failure(symbol)
                if self._circuit_breaker.is_open(symbol):
                    logger.warning(
                        "Analyst circuit opened for %s after %d consecutive parse"
                        " failures; suppressing LLM calls for %d cycles",
                        symbol,
                        failures,
                        self._circuit_breaker.cooldown_cycles,
                        extra={"symbol": symbol, "agent": "analyst"},
                    )
            return AnalystPipelineResultSchema(
                decision=None,
                regime=regime,
                stop=True,
                cached=False,
                reason="agent_error",
                regime_gate=regime_gate,
            )

        # Record the bar we just analyzed so subsequent cycles within the
        # same candle can short-circuit via the dedup hit above.
        self._dedup.cache_analyst(symbol, bar_close=current_bar, result=result)
        self._circuit_breaker.reset(symbol)
        return self._apply_confluence_gate(
            symbol,
            decision=result,
            regime=regime,
            htf_trend=deps.htf_trend,
            regime_gate=regime_gate,
            cached=False,
        )

    def _apply_confluence_gate(
        self,
        symbol: str,
        *,
        decision: AnalystDecisionSchema,
        regime: VolatilityRegime,
        htf_trend: HtfTrendSchema | None,
        regime_gate: int,
        cached: bool,
    ) -> AnalystPipelineResultSchema:
        """Apply the regime-specific escalation gate + optional override.

        ``regime_gate`` is the regime's gate (NORMAL=6, HIGH=7, EXTREME=8,
        LOW=7) already scaled to the available signals. The confluence
        override (e.g. elevated-fear FGI gate) can tighten the gate further
        but never loosen it.
        """
        confluence_gate = regime_gate
        if self._confluence_override is not None:
            override = self._confluence_override.get_confluence_override(
                decision.direction
            )
            if override is not None:
                confluence_gate = max(confluence_gate, override)

        # HTF soft gate: a setup fighting the 1h trend must clear a bar one
        # point higher. Counter-trend entries can still pass on genuinely
        # strong confluence; weak ones against the higher timeframe are cut.
        if (
            htf_trend is not None
            and htf_trend.direction in {"LONG", "SHORT"}
            and decision.direction in {"LONG", "SHORT"}
            and htf_trend.direction != decision.direction
        ):
            confluence_gate += COUNTER_TREND_GATE_BUMP
            logger.info(
                "HTF counter-trend gate for %s: analyst=%s vs 1h=%s — gate bumped=%d",
                symbol,
                decision.direction,
                htf_trend.direction,
                confluence_gate,
                extra={"symbol": symbol, "agent": "analyst"},
            )

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
                regime_gate=regime_gate,
            )
        return AnalystPipelineResultSchema(
            decision=decision,
            regime=regime,
            stop=False,
            cached=cached,
            reason="ok",
            regime_gate=regime_gate,
        )

    @staticmethod
    def _log_scaled_gates(
        symbol: str,
        regime: VolatilityRegime,
        available: int,
        regime_gate: int,
        *,
        min_algo: int,
    ) -> None:
        base_gate = confluence_enter_min_for_regime(regime)
        if regime_gate >= base_gate:
            return
        logger.info(
            "Confluence gates scaled for %s: %d/8 signals available,"
            " regime gate %d -> %d, min algo %d",
            symbol,
            available,
            base_gate,
            regime_gate,
            min_algo,
            extra={
                "symbol": symbol,
                "agent": "analyst",
                "available_signals": available,
                "base_gate": base_gate,
                "effective_gate": regime_gate,
                "effective_min_algo": min_algo,
            },
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
