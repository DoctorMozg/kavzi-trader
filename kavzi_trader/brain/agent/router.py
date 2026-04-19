import hashlib
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Protocol

import httpx
import openai
from pydantic import BaseModel, ConfigDict
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
from kavzi_trader.brain.schemas.analyst import (
    AnalystDecisionSchema,
    KeyLevelSchema,
)
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


class _TraderRunResult(BaseModel):
    decision: TradeDecisionSchema | None = None
    deps: TradingDependenciesSchema | None = None
    model_config = ConfigDict(frozen=True)


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
        count. Called by the LLM-exception path inside ``_run_trader`` and by
        the reasoning loop when downstream schema validation rejects a
        malformed decision (e.g. missing stop_loss/take_profit).
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

    def _reset_trader_failures(self, symbol: str) -> None:
        """Clear the Trader failure counter after a successful decision."""
        if self._circuit_breaker.failure_count(symbol) > 0:
            self._circuit_breaker.reset(symbol)
            logger.info(
                "Trader validation failure counter cleared for %s after"
                " successful decision",
                symbol,
            )

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

        trader_run = await self._run_trader(
            symbol,
            deps_provider,
            analyst_decision,
            scout_pattern=scout_result.pattern_detected,
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

    async def _run_trader(
        self,
        symbol: str,
        deps_provider: DependenciesProvider,
        analyst_result: AnalystDecisionSchema,
        scout_pattern: str | None = None,
    ) -> _TraderRunResult:
        deps = await deps_provider.get_trader(symbol)

        if not deps.recent_candles:
            logger.warning(
                "Trader deps for %s have no candles; returning empty result",
                symbol,
            )
            return _TraderRunResult()

        circuit_wait = self._circuit_breaker_wait(symbol)
        if circuit_wait is not None:
            return _TraderRunResult(decision=circuit_wait, deps=deps)

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
            return _TraderRunResult(decision=cached, deps=deps)

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
            return _TraderRunResult(decision=gate_reject, deps=deps)

        return await self._invoke_trader_llm(
            symbol, deps, analyst_result, scout_pattern, analyst_hash, current_bar
        )

    def _circuit_breaker_wait(self, symbol: str) -> TradeDecisionSchema | None:
        """Return a WAIT decision when the Trader circuit is open, else None.

        The WAIT is intentionally NOT cached — the reasoning loop treats it
        as a non-enqueued cycle, and the next successful call must reset the
        circuit counter via `_reset_trader_failures`.
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
        breakout_reject = self._pre_trader_breakout_check(
            symbol,
            scout_pattern,
            deps,
            analyst_direction=analyst_result.direction,
        )
        if breakout_reject is not None:
            return breakout_reject
        return self._pre_trader_rr_check(
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
    ) -> _TraderRunResult:
        """Call the Trader LLM with full error handling.

        * Success → cache result, reset failure counter.
        * Timeout / UnexpectedModelBehavior → WAIT, no cache (M1), counter
          increments on UnexpectedModelBehavior only.
        * Other Exception → empty result, no cache.
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
            return _TraderRunResult(
                decision=self._build_timeout_wait(symbol, elapsed_ms),
                deps=deps,
            )
        except UnexpectedModelBehavior as exc:
            return _TraderRunResult(
                decision=self._build_unexpected_model_wait(symbol, exc, t0),
                deps=deps,
            )
        except Exception as exc:  # noqa: BLE001 - LLM client raises many types
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._log_llm_exception(symbol, "trader", exc, elapsed_ms)
            return _TraderRunResult()
        self._dedup.cache_trader(
            symbol,
            analyst_hash=analyst_hash,
            bar_close=current_bar,
            decision=result,
        )
        self._reset_trader_failures(symbol)
        return _TraderRunResult(decision=result, deps=deps)

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
        failure_count = self.record_trader_validation_failure(symbol)
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

    def _pre_trader_breakout_check(
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
                " — approaching overextension zone",
                symbol,
                float(percent_b),
                analyst_direction,
            )
        return None

    @staticmethod
    def _estimate_rr(
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

    def _pre_trader_rr_check(
        self,
        symbol: str,
        analyst_result: AnalystDecisionSchema,
        current_price: Decimal,
        atr: Decimal | None,
    ) -> TradeDecisionSchema | None:
        """Pre-Trader estimated R/R gate.

        * NEUTRAL direction or missing ATR → fail open (return None).
        * estimated R/R < `rr_hard_block` (0.5) → return a WAIT decision.
          The geometry implied by the Analyst's key levels is
          statistically guaranteed to lose at current TP-hit rates, so we
          skip the Trader LLM call entirely to conserve budget.
        * `rr_hard_block` ≤ R/R < `rr_min_prescreen` → log a warning and
          proceed to the Trader for final assessment.
        * R/R ≥ `rr_min_prescreen` → proceed silently.
        """
        if analyst_result.direction == "NEUTRAL":
            return None
        estimated_rr = AgentRouter._estimate_rr(
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
                " — skipping Trader call and returning WAIT",
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
                " — proceeding to Trader for final assessment",
                symbol,
                float(estimated_rr),
                float(rr_min_prescreen),
            )
        return None

    @staticmethod
    def _log_stop(agent: str, symbol: str, start: float) -> None:
        total_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Pipeline stopped at %s for %s in %.1fms",
            agent,
            symbol,
            total_ms,
        )
