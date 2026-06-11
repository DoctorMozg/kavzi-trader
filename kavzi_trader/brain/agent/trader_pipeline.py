import hashlib
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.exceptions import UnexpectedModelBehavior

from kavzi_trader.brain.agent.circuit_breaker import AgentCircuitBreaker
from kavzi_trader.brain.agent.decision_dedup import DecisionDeduplicator
from kavzi_trader.brain.agent.router_config import RouterConfigSchema
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema
from kavzi_trader.spine.execution.geometry import TradeGeometryCalculator
from kavzi_trader.spine.execution.geometry_schemas import (
    GeometryInputsSchema,
    GeometryRejectionSchema,
    TradeGeometrySchema,
)

logger = logging.getLogger(__name__)


def _wait_decision(reasoning: str, confidence: float = 0.0) -> TradeDecisionSchema:
    """Build a structure-less WAIT decision for deterministic reject paths."""
    return TradeDecisionSchema(
        action="WAIT",
        confidence=confidence,
        reasoning=reasoning,
        entry_tactic=None,
        entry_level_index=None,
        stop_level_index=None,
        stop_atr_multiplier=None,
        target_style=None,
    )


def _geometry_inputs(
    analyst_result: AnalystDecisionSchema,
    deps: TradingDependenciesSchema,
) -> GeometryInputsSchema:
    """Assemble geometry-calculator inputs from the pipeline context."""
    return GeometryInputsSchema(
        symbol=deps.symbol,
        current_price=deps.current_price,
        atr_14=deps.indicators.atr_14,
        key_levels=analyst_result.key_levels.levels,
        leverage=deps.leverage,
    )


class TraderRunner(Protocol):
    async def run(
        self,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema | None = None,
        scout_pattern: str | None = None,
    ) -> TradeDecisionSchema: ...


class TraderDepsFetcher(Protocol):
    async def get_trader(self, symbol: str) -> TradingDependenciesSchema: ...


class LLMExceptionLogger(Protocol):
    def __call__(
        self,
        symbol: str,
        agent: str,
        exc: BaseException,
        elapsed_ms: float,
    ) -> None: ...


_TraderStopReason = Literal[
    "no_candles",
    "circuit_open",
    "dedup_hit",
    "pre_trade_gate_reject",
    "geometry_reject",
    "structure_invalid",
    "llm_timeout",
    "llm_unexpected_model",
    "llm_error",
    "ok",
]


class TraderPipelineResultSchema(BaseModel):
    """Outcome of the Trader pipeline stage.

    Carries everything ``AgentRouter.run`` needs to build the final
    ``PipelineResult``. ``decision`` is None when the Trader was not
    invoked (e.g. empty candles, unhandled exception); otherwise it is a
    real Trader decision, a cached dedup hit, a deterministic gate WAIT,
    a circuit-open WAIT, or an LLM-failure fallback WAIT.

    ``deps`` is None only when ``get_trader`` returned empty candles or
    the Trader raised a generic unhandled exception.

    ``geometry`` carries the concrete entry/SL/TP derived for an actionable
    LONG/SHORT decision; it is None for WAIT/CLOSE and every reject path.
    """

    decision: Annotated[TradeDecisionSchema | None, Field(default=None)]
    deps: Annotated[TradingDependenciesSchema | None, Field(default=None)]
    geometry: Annotated[TradeGeometrySchema | None, Field(default=None)]
    cached: Annotated[bool, Field(default=False)]
    reason: Annotated[_TraderStopReason, Field(...)]

    model_config = ConfigDict(frozen=True)


class TraderPipeline:
    """Orchestrates the Trader stage: circuit, dedup, gates, guarded invoke.

    Extracted from ``AgentRouter`` so the router's ``run`` method can
    delegate Trader orchestration in one call and concentrate on tier
    transitions. Owns the circuit-breaker short-circuit, 3-tuple dedup,
    deterministic pre-trade gates (breakout %B, geometry viability), guarded
    LLM invocation, and the geometry-derivation step that turns the Trader's
    structural choice into concrete prices.
    """

    def __init__(
        self,
        trader: TraderRunner,
        dedup: DecisionDeduplicator,
        circuit_breaker: AgentCircuitBreaker,
        router_config: RouterConfigSchema,
        log_llm_exception: LLMExceptionLogger,
        geometry: TradeGeometryCalculator,
    ) -> None:
        self._trader = trader
        self._dedup = dedup
        self._circuit_breaker = circuit_breaker
        self._router_config = router_config
        self._log_llm_exception = log_llm_exception
        self._geometry = geometry

    async def run(
        self,
        symbol: str,
        analyst_result: AnalystDecisionSchema,
        scout_pattern: str | None,
        deps_provider: TraderDepsFetcher,
    ) -> TraderPipelineResultSchema:
        """Execute the Trader stage for ``symbol``.

        * Fetches Trader dependencies; short-circuits on empty candles.
        * Short-circuits with a WAIT when the symbol's circuit is open.
        * Consults the dedup cache keyed on
          (symbol, analyst_hash, bar_close).
        * Runs deterministic pre-Trader gates (breakout %B, geometry
          viability). Gate rejects are cached so the cycle doesn't
          re-evaluate gates on the next invocation within the same bar.
        * Otherwise invokes the Trader LLM under full error handling, then
          derives concrete geometry for actionable decisions; caches only
          successful decisions and resets the circuit counter on success.
        """
        deps = await deps_provider.get_trader(symbol)

        if not deps.recent_candles:
            logger.warning(
                "Trader deps for %s have no candles; returning empty result",
                symbol,
            )
            return TraderPipelineResultSchema(
                decision=None,
                deps=None,
                geometry=None,
                cached=False,
                reason="no_candles",
            )

        circuit_wait = self._circuit_breaker_wait(symbol)
        if circuit_wait is not None:
            return TraderPipelineResultSchema(
                decision=circuit_wait,
                deps=deps,
                geometry=None,
                cached=False,
                reason="circuit_open",
            )

        current_bar = deps.recent_candles[-1].close_time
        analyst_hash = self._hash_analyst(analyst_result)
        cached = self._dedup.trader_hit(symbol, analyst_hash, current_bar)
        if cached is not None:
            logger.info(
                "Trader dedup hit for %s: analyst_hash=%s bar=%s action=%s",
                symbol,
                analyst_hash[:8],
                current_bar,
                cached.decision.action,
                extra={"symbol": symbol, "agent": "trader", "dedup": "hit"},
            )
            return TraderPipelineResultSchema(
                decision=cached.decision,
                deps=deps,
                geometry=cached.geometry,
                cached=True,
                reason="dedup_hit",
            )

        self._log_trader_inputs(deps, analyst_result, scout_pattern)

        gate_reject = self._check_pre_trader_gates(
            symbol, scout_pattern, analyst_result, deps
        )
        if gate_reject is not None:
            self._dedup.cache_trader(
                symbol,
                analyst_hash=analyst_hash,
                bar_close=current_bar,
                decision=gate_reject,
            )
            return TraderPipelineResultSchema(
                decision=gate_reject,
                deps=deps,
                geometry=None,
                cached=False,
                reason="pre_trade_gate_reject",
            )

        return await self._invoke_trader_llm(
            symbol,
            deps,
            analyst_result,
            scout_pattern,
            analyst_hash,
            current_bar,
        )

    def _circuit_breaker_wait(self, symbol: str) -> TradeDecisionSchema | None:
        """Return a WAIT decision when the Trader circuit is open, else None.

        The WAIT is intentionally NOT cached — the reasoning loop treats it
        as a non-enqueued cycle, and the next successful call must reset the
        circuit counter via :meth:`_reset_trader_failures`.
        """
        if not self._circuit_breaker.is_open(symbol):
            return None
        failures = self._circuit_breaker.failure_count(symbol)
        threshold = self._circuit_breaker.threshold
        logger.warning(
            "Trader circuit open for %s: %d consecutive validation"
            " failures ≥ threshold %d — skipping Trader call",
            symbol,
            failures,
            threshold,
            extra={
                "symbol": symbol,
                "agent": "trader",
                "trader_circuit_open": True,
                "trader_validation_failures_total": failures,
            },
        )
        return _wait_decision(
            f"Trader circuit breaker open for {symbol}:"
            f" {failures} consecutive validation failures reached"
            f" threshold {threshold}."
            f" Suspending Trader calls until a successful"
            f" decision resets the counter."
        )

    @staticmethod
    def _hash_analyst(analyst_result: AnalystDecisionSchema) -> str:
        """sha1 of the serialized Analyst result, used purely as a dedup key."""
        return hashlib.sha1(
            analyst_result.model_dump_json().encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()

    def _check_pre_trader_gates(
        self,
        symbol: str,
        scout_pattern: str | None,
        analyst_result: AnalystDecisionSchema,
        deps: TradingDependenciesSchema,
    ) -> TradeDecisionSchema | None:
        """Run deterministic pre-Trader gates. Returns a WAIT decision if
        any gate rejects, else None to proceed to the LLM call.
        """
        breakout_reject = self.pre_trader_breakout_check(
            symbol,
            scout_pattern,
            deps,
            analyst_direction=analyst_result.direction,
        )
        if breakout_reject is not None:
            return breakout_reject
        return self.pre_trader_viability_check(symbol, analyst_result, deps)

    async def _invoke_trader_llm(
        self,
        symbol: str,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema,
        scout_pattern: str | None,
        analyst_hash: str,
        current_bar: datetime,
    ) -> TraderPipelineResultSchema:
        """Call the Trader LLM with full error handling.

        * Success -> derive geometry, cache, reset failure counter.
        * Timeout / UnexpectedModelBehavior -> WAIT, no cache, counter
          increments on UnexpectedModelBehavior only.
        * Other Exception -> empty result, no cache.
        """
        t0 = time.monotonic()
        try:
            result = await self._trader.run(
                deps,
                analyst_result=analyst_result,
                scout_pattern=scout_pattern,
            )
        except (TimeoutError, httpx.TimeoutException) as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._log_llm_exception(symbol, "trader", exc, elapsed_ms)
            return TraderPipelineResultSchema(
                decision=self._build_timeout_wait(elapsed_ms),
                deps=deps,
                geometry=None,
                cached=False,
                reason="llm_timeout",
            )
        except UnexpectedModelBehavior as exc:
            return TraderPipelineResultSchema(
                decision=self._build_unexpected_model_wait(symbol, exc, t0),
                deps=deps,
                geometry=None,
                cached=False,
                reason="llm_unexpected_model",
            )
        except Exception as exc:  # noqa: BLE001 - LLM client raises many types
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._log_llm_exception(symbol, "trader", exc, elapsed_ms)
            return TraderPipelineResultSchema(
                decision=None,
                deps=None,
                geometry=None,
                cached=False,
                reason="llm_error",
            )
        return self._finalize_trader_decision(
            symbol, deps, analyst_result, result, analyst_hash, current_bar
        )

    def _finalize_trader_decision(
        self,
        symbol: str,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema,
        result: TradeDecisionSchema,
        analyst_hash: str,
        current_bar: datetime,
    ) -> TraderPipelineResultSchema:
        """Derive concrete geometry for actionable decisions.

        * WAIT / CLOSE -> cache and pass through, no geometry needed.
        * LONG / SHORT -> compute prices from the chosen structure.
          INVALID_STRUCTURE (bad level index) counts as a Trader validation
          failure and is NOT cached, so a fresh LLM call next cycle can pick
          a valid anchor. Market-condition rejections (stop too wide, target
          unreachable, liquidation budget) become cached WAITs — same bar,
          same data, same outcome.
        """
        if result.action not in {"LONG", "SHORT"}:
            self._dedup.cache_trader(
                symbol,
                analyst_hash=analyst_hash,
                bar_close=current_bar,
                decision=result,
            )
            self._reset_trader_failures(symbol)
            return TraderPipelineResultSchema(
                decision=result,
                deps=deps,
                geometry=None,
                cached=False,
                reason="ok",
            )

        outcome = self._geometry.compute(
            result.to_structure(),
            _geometry_inputs(analyst_result, deps),
        )
        if isinstance(outcome, GeometryRejectionSchema):
            wait = _wait_decision(
                f"Trader chose {result.action} but geometry was rejected"
                f" ({outcome.code}): {outcome.detail}"
            )
            if outcome.code == "INVALID_STRUCTURE":
                self._record_trader_validation_failure(symbol)
                return TraderPipelineResultSchema(
                    decision=wait,
                    deps=deps,
                    geometry=None,
                    cached=False,
                    reason="structure_invalid",
                )
            self._dedup.cache_trader(
                symbol,
                analyst_hash=analyst_hash,
                bar_close=current_bar,
                decision=wait,
            )
            self._reset_trader_failures(symbol)
            return TraderPipelineResultSchema(
                decision=wait,
                deps=deps,
                geometry=None,
                cached=False,
                reason="geometry_reject",
            )

        logger.info(
            "Trader geometry for %s: %s entry=%s sl=%s tp=%s rr=%s adj=%s",
            symbol,
            result.action,
            outcome.entry,
            outcome.stop_loss,
            outcome.take_profit,
            outcome.rr_ratio,
            outcome.adjustments,
            extra={"symbol": symbol, "agent": "trader"},
        )
        self._dedup.cache_trader(
            symbol,
            analyst_hash=analyst_hash,
            bar_close=current_bar,
            decision=result,
            geometry=outcome,
        )
        self._reset_trader_failures(symbol)
        return TraderPipelineResultSchema(
            decision=result,
            deps=deps,
            geometry=outcome,
            cached=False,
            reason="ok",
        )

    def _reset_trader_failures(self, symbol: str) -> None:
        """Clear the Trader failure counter after a successful decision."""
        if self._circuit_breaker.failure_count(symbol) > 0:
            self._circuit_breaker.reset(symbol)
            logger.info(
                "Trader validation failure counter cleared for %s after"
                " successful decision",
                symbol,
            )

    @staticmethod
    def _build_timeout_wait(elapsed_ms: float) -> TradeDecisionSchema:
        return _wait_decision(
            f"Trader agent timed out after {elapsed_ms / 1000:.1f}s."
            " Returning WAIT to avoid stale entry."
            " Consider lowering trader timeout_s or using a"
            " faster model."
        )

    def _build_unexpected_model_wait(
        self,
        symbol: str,
        exc: UnexpectedModelBehavior,
        t0: float,
    ) -> TradeDecisionSchema:
        elapsed_ms = (time.monotonic() - t0) * 1000
        failure_count = self._record_trader_validation_failure(symbol)
        self._log_llm_exception(symbol, "trader", exc, elapsed_ms)
        # Augment with the validation-failure counter the helper doesn't
        # track. Emitted once per unparseable response so the circuit
        # breaker state is visible alongside the raw body.
        logger.warning(
            "Trader validation retries exhausted for %s (total=%d): %s",
            symbol,
            failure_count,
            exc.message,
            extra={
                "symbol": symbol,
                "agent": "trader",
                "trader_validation_failures_total": failure_count,
                "exception_type": type(exc).__name__,
            },
        )
        return _wait_decision(
            f"Trader model returned unparseable output after"
            f" {elapsed_ms / 1000:.1f}s. Raw body logged for debugging."
            f" Returning WAIT to avoid acting on malformed data."
        )

    def _record_trader_validation_failure(self, symbol: str) -> int:
        """Increment the per-symbol Trader failure counter and return total."""
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

    @staticmethod
    def _log_trader_inputs(
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema,
        scout_pattern: str | None,
    ) -> None:
        ind = deps.indicators
        of = deps.order_flow
        conf = deps.algorithm_confluence
        logger.info(
            "Trader inputs %s: price=%s regime=%s RSI=%s "
            "MACD=%s BB%%b=%s vol=%s funding=%s OI_1h=%s "
            "L/S=%s conf=%s/%s(%s) analyst=%s(%d) "
            "pattern=%s pos=%d bal=%s sent=%s '%s'",
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
            analyst_result.direction,
            analyst_result.confluence_score,
            scout_pattern,
            len(deps.open_positions),
            deps.account_state.available_balance_usdt,
            deps.sentiment_summary.sentiment_bias if deps.sentiment_summary else None,
            deps.sentiment_summary.summary[:30] if deps.sentiment_summary else "",
        )

    def pre_trader_breakout_check(
        self,
        symbol: str,
        scout_pattern: str | None,
        deps: TradingDependenciesSchema,
        *,
        analyst_direction: str,
    ) -> TradeDecisionSchema | None:
        """Reject BREAKOUT entries when %B indicates overextension."""
        if scout_pattern != "BREAKOUT":
            return None
        bb = deps.indicators.bollinger
        if bb is None:
            return None
        percent_b = bb.percent_b

        overextended_long = self._router_config.breakout_overextended_b_long
        overextended_short = self._router_config.breakout_overextended_b_short

        is_short = analyst_direction == "SHORT"
        if is_short:
            overextended = percent_b < overextended_short
        else:
            overextended = percent_b > overextended_long

        if overextended:
            if is_short:
                threshold = overextended_short
                band_desc = "below the lower band"
            else:
                threshold = overextended_long
                band_desc = "beyond the upper band"
            logger.info(
                "Pre-Trader BREAKOUT reject for %s: %%B=%.2f,"
                " direction=%s — price overextended %s",
                symbol,
                float(percent_b),
                analyst_direction,
                band_desc,
            )
            return _wait_decision(
                f"Deterministic pre-Trader reject: BREAKOUT pattern with"
                f" Bollinger %%B={float(percent_b):.2f} exceeds"
                f" {float(threshold):.2f} overextension"
                f" threshold. Price is too far {band_desc} for"
                f" a sustainable breakout entry."
            )

        if is_short:
            in_caution = (
                percent_b < Decimal("-0.10") and percent_b >= overextended_short
            )
        else:
            in_caution = percent_b > Decimal("1.10") and percent_b <= overextended_long
        if in_caution:
            logger.warning(
                "BREAKOUT caution for %s: %%B=%.2f, direction=%s"
                " — approaching overextension zone",
                symbol,
                float(percent_b),
                analyst_direction,
            )
        return None

    def pre_trader_viability_check(
        self,
        symbol: str,
        analyst_result: AnalystDecisionSchema,
        deps: TradingDependenciesSchema,
    ) -> TradeDecisionSchema | None:
        """Skip the Trader LLM when no legal geometry can reach min R:R.

        Uses the geometry calculator's estimate mode (tightest legal stop
        against the best available target), so a block here means even the
        most favourable structural choice cannot produce a viable trade.
        NEUTRAL fails open — there is no direction to size against.
        """
        if analyst_result.direction == "NEUTRAL":
            return None
        viability = self._geometry.estimate(
            analyst_result.direction,
            _geometry_inputs(analyst_result, deps),
        )
        if viability.viable:
            return None
        logger.warning(
            "Pre-Trader viability block for %s: %s",
            symbol,
            viability.reason,
            extra={"symbol": symbol, "agent": "trader"},
        )
        return _wait_decision(
            f"Pre-trader viability block: {viability.reason}"
            f" Skipping Trader call — no structural choice can produce"
            f" a valid trade here."
        )
