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
from kavzi_trader.brain.schemas.analyst import (
    AnalystDecisionSchema,
    KeyLevelSchema,
)
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema

logger = logging.getLogger(__name__)


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
    """

    decision: Annotated[TradeDecisionSchema | None, Field(default=None)]
    deps: Annotated[TradingDependenciesSchema | None, Field(default=None)]
    cached: Annotated[bool, Field(default=False)]
    reason: Annotated[_TraderStopReason, Field(...)]

    model_config = ConfigDict(frozen=True)


class TraderPipeline:
    """Orchestrates the Trader stage: circuit, dedup, gates, guarded invoke.

    Extracted from ``AgentRouter`` so the router's ``run`` method can
    delegate Trader orchestration in one call and concentrate on tier
    transitions. Preserves the original behaviour exactly — including log
    messages, circuit-breaker semantics, dedup semantics (3-tuple key of
    ``symbol`` / ``analyst_hash`` / ``bar_close``), deterministic
    pre-trade gates (breakout %B, R/R), and LLM-failure fallbacks.
    """

    def __init__(
        self,
        trader: TraderRunner,
        dedup: DecisionDeduplicator,
        circuit_breaker: AgentCircuitBreaker,
        router_config: RouterConfigSchema,
        log_llm_exception: LLMExceptionLogger,
    ) -> None:
        self._trader = trader
        self._dedup = dedup
        self._circuit_breaker = circuit_breaker
        self._router_config = router_config
        self._log_llm_exception = log_llm_exception

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
        * Runs deterministic pre-Trader gates (breakout %B, R/R). Gate
          rejects are cached so the cycle doesn't re-evaluate gates on
          the next invocation within the same bar.
        * Otherwise invokes the Trader LLM under full error handling;
          caches only successful decisions and resets the circuit
          counter on success.
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
                cached=False,
                reason="no_candles",
            )

        circuit_wait = self._circuit_breaker_wait(symbol)
        if circuit_wait is not None:
            return TraderPipelineResultSchema(
                decision=circuit_wait,
                deps=deps,
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
                cached.action,
                extra={"symbol": symbol, "agent": "trader", "dedup": "hit"},
            )
            return TraderPipelineResultSchema(
                decision=cached,
                deps=deps,
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
            " failures \u2265 threshold %d \u2014 skipping Trader call",
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
        return TradeDecisionSchema(
            action="WAIT",
            confidence=0.0,
            reasoning=(
                f"Trader circuit breaker open for {symbol}:"
                f" {failures} consecutive validation failures reached"
                f" threshold {threshold}."
                f" Suspending Trader calls until a successful"
                f" decision resets the counter."
            ),
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
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
        return self.pre_trader_rr_check(
            symbol,
            analyst_result,
            deps.current_price,
            deps.indicators.atr_14,
        )

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

        * Success -> cache result, reset failure counter.
        * Timeout / UnexpectedModelBehavior -> WAIT, no cache (M1), counter
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
                decision=self._build_timeout_wait(symbol, elapsed_ms),
                deps=deps,
                cached=False,
                reason="llm_timeout",
            )
        except UnexpectedModelBehavior as exc:
            return TraderPipelineResultSchema(
                decision=self._build_unexpected_model_wait(symbol, exc, t0),
                deps=deps,
                cached=False,
                reason="llm_unexpected_model",
            )
        except Exception as exc:  # noqa: BLE001 - LLM client raises many types
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._log_llm_exception(symbol, "trader", exc, elapsed_ms)
            return TraderPipelineResultSchema(
                decision=None,
                deps=None,
                cached=False,
                reason="llm_error",
            )
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
    def _build_timeout_wait(symbol: str, elapsed_ms: float) -> TradeDecisionSchema:
        _ = symbol  # logging handled by caller via _log_llm_exception
        return TradeDecisionSchema(
            action="WAIT",
            confidence=0.0,
            reasoning=(
                f"Trader agent timed out after {elapsed_ms / 1000:.1f}s."
                " Returning WAIT to avoid stale entry."
                " Consider lowering trader timeout_s or using a"
                " faster model."
            ),
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
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
        return TradeDecisionSchema.model_validate(
            {
                "action": "WAIT",
                "confidence": 0,
                "reasoning": (
                    f"Trader model returned unparseable output after"
                    f" {elapsed_ms / 1000:.1f}s. Raw body logged for debugging."
                    f" Returning WAIT to avoid acting on malformed data."
                ),
                "suggested_entry": None,
                "suggested_stop_loss": None,
                "suggested_take_profit": None,
            }
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
                " direction=%s \u2014 price overextended %s",
                symbol,
                float(percent_b),
                analyst_direction,
                band_desc,
            )
            return TradeDecisionSchema(
                action="WAIT",
                confidence=0.0,
                reasoning=(
                    f"Deterministic pre-Trader reject: BREAKOUT pattern with"
                    f" Bollinger %%B={float(percent_b):.2f} exceeds"
                    f" {float(threshold):.2f} overextension"
                    f" threshold. Price is too far {band_desc} for"
                    f" a sustainable breakout entry."
                ),
                suggested_entry=None,
                suggested_stop_loss=None,
                suggested_take_profit=None,
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
                " \u2014 approaching overextension zone",
                symbol,
                float(percent_b),
                analyst_direction,
            )
        return None

    @staticmethod
    def estimate_rr(
        direction: str,
        current_price: Decimal,
        key_levels: list[KeyLevelSchema],
        atr: Decimal | None,
    ) -> Decimal | None:
        """Estimate risk/reward from key levels with ATR fallback."""
        if atr is None or atr == 0:
            return None
        if direction == "NEUTRAL":
            return None

        supports = [lv.price for lv in key_levels if lv.level_type == "SUPPORT"]
        resistances = [lv.price for lv in key_levels if lv.level_type == "RESISTANCE"]

        if direction == "LONG":
            sl_candidates = [p for p in supports if p < current_price]
            tp_candidates = [p for p in resistances if p > current_price]
            sl = max(sl_candidates) if sl_candidates else current_price - atr
            tp = min(tp_candidates) if tp_candidates else current_price + 2 * atr
        else:  # SHORT
            sl_candidates = [p for p in resistances if p > current_price]
            tp_candidates = [p for p in supports if p < current_price]
            sl = min(sl_candidates) if sl_candidates else current_price + atr
            tp = max(tp_candidates) if tp_candidates else current_price - 2 * atr

        risk = abs(current_price - sl)
        reward = abs(tp - current_price)
        if risk == 0:
            return None
        return reward / risk

    def pre_trader_rr_check(
        self,
        symbol: str,
        analyst_result: AnalystDecisionSchema,
        current_price: Decimal,
        atr: Decimal | None,
    ) -> TradeDecisionSchema | None:
        """Pre-Trader estimated R/R gate.

        * NEUTRAL direction or missing ATR -> fail open (return None).
        * estimated R/R < ``rr_hard_block`` (0.5) -> return a WAIT
          decision. The geometry implied by the Analyst's key levels is
          statistically guaranteed to lose at current TP-hit rates, so we
          skip the Trader LLM call entirely to conserve budget.
        * ``rr_hard_block`` <= R/R < ``rr_min_prescreen`` -> log a warning
          and proceed to the Trader for final assessment.
        * R/R >= ``rr_min_prescreen`` -> proceed silently.
        """
        if analyst_result.direction == "NEUTRAL":
            return None
        estimated_rr = TraderPipeline.estimate_rr(
            analyst_result.direction,
            current_price,
            analyst_result.key_levels.levels,
            atr,
        )
        if estimated_rr is None:
            return None  # Fail open when we cannot estimate

        rr_hard_block = self._router_config.rr_hard_block
        rr_min_prescreen = self._router_config.rr_min_prescreen

        if estimated_rr < rr_hard_block:
            logger.warning(
                "Pre-Trader R/R hard block for %s: estimated R/R=%.2f < %.2f"
                " \u2014 skipping Trader call and returning WAIT",
                symbol,
                float(estimated_rr),
                float(rr_hard_block),
            )
            return TradeDecisionSchema(
                action="WAIT",
                confidence=0.0,
                reasoning=(
                    f"Pre-trader R/R {float(estimated_rr):.2f} below"
                    f" {float(rr_hard_block):.2f} hard block; analyst key"
                    f" levels yield insufficient reward relative to risk."
                    f" Skipping Trader call to conserve budget and protect"
                    f" against statistically-losing geometry."
                ),
                suggested_entry=None,
                suggested_stop_loss=None,
                suggested_take_profit=None,
            )

        if estimated_rr < rr_min_prescreen:
            logger.warning(
                "Pre-Trader R/R warning for %s: estimated R/R=%.2f < %.1f"
                " \u2014 proceeding to Trader for final assessment",
                symbol,
                float(estimated_rr),
                float(rr_min_prescreen),
            )
        return None
