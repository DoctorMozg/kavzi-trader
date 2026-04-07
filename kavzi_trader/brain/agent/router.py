import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from kavzi_trader.brain.schemas.analyst import (
    AnalystDecisionSchema,
    KeyLevelSchema,
    KeyLevelsSchema,
)
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema

logger = logging.getLogger(__name__)

_SKIP_ERROR = ScoutDecisionSchema(
    verdict="SKIP",
    reason="agent_error",
    pattern_detected=None,
)


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


_DEFAULT_ANALYST_MIN_ALGO_CONFLUENCE = 3

# Minimum Analyst confluence_score required to escalate to the Trader tier.
# Combined with the LLM's own setup_valid flag, this forms a hysteresis gate:
# scores 4-5 are treated as "borderline WAIT" in the reasoning loop so that
# LLM sampling noise cannot flip the pipeline between enter and reject on
# identical inputs. The threshold is aligned with the prompt's own "mark
# setup_valid=true iff confluence >= 6" rubric, and bar-close dedup in the
# router prevents intra-bar re-analysis.
_ANALYST_CONFLUENCE_ENTER = 6

# Pre-Trader deterministic gates
_BREAKOUT_OVEREXTENDED_B = Decimal("1.20")
_RR_MIN_PRESCREEN = Decimal("1.2")


class AgentRouter:
    def __init__(
        self,
        scout: ScoutRunner,
        analyst: AnalystRunner,
        trader: TraderRunner,
        analyst_min_algo_confluence: int = _DEFAULT_ANALYST_MIN_ALGO_CONFLUENCE,
        confluence_override: ConfluenceOverrideProvider | None = None,
    ) -> None:
        self._scout = scout
        self._analyst = analyst
        self._trader = trader
        self._analyst_min_algo_confluence = analyst_min_algo_confluence
        self._confluence_override = confluence_override
        # Per-symbol bar-close dedup for Scout (deterministic — safe to cache
        # both INTERESTING and SKIP within the same candle).
        self._last_scout_bar_close: dict[str, datetime] = {}
        self._last_scout_result: dict[str, ScoutDecisionSchema] = {}
        # Per-symbol bar-close dedup for Analyst (LLM-based).
        self._last_analyzed_bar_close: dict[str, datetime] = {}
        self._last_analyst_result: dict[str, AnalystDecisionSchema] = {}

    async def run(
        self,
        symbol: str,
        deps_provider: DependenciesProvider,
    ) -> PipelineResult:
        total_start = time.monotonic()
        logger.info("Agent pipeline started for %s", symbol)

        scout_deps = await self._fetch_scout_deps(symbol, deps_provider)

        # Scout bar-close dedup: deterministic filter produces the same
        # verdict for the same candle, so cache both INTERESTING and SKIP.
        current_scout_bar = scout_deps.recent_candles[-1].close_time
        prev_scout_bar = self._last_scout_bar_close.get(symbol)
        cached_scout = (
            self._last_scout_result.get(symbol)
            if prev_scout_bar is not None and current_scout_bar == prev_scout_bar
            else None
        )
        if cached_scout is not None:
            logger.info(
                "Scout dedup hit for %s: bar close_time=%s already"
                " evaluated (cached verdict=%s)",
                symbol,
                current_scout_bar,
                cached_scout.verdict,
            )
            scout_result: ScoutDecisionSchema = cached_scout
        else:
            raw = await self._invoke_scout(symbol, scout_deps)
            scout_result = raw if raw is not None else _SKIP_ERROR
            self._last_scout_bar_close[symbol] = current_scout_bar
            self._last_scout_result[symbol] = scout_result

        if scout_result.verdict != "INTERESTING":
            self._log_stop("Scout", symbol, total_start)
            return PipelineResult(scout=scout_result)

        analyst_result = await self._run_analyst(symbol, deps_provider)
        if analyst_result is None:
            return PipelineResult(scout=scout_result)

        # FGI elevated-fear confluence override: raise the entry gate when
        # market fear is elevated but not extreme (already blocked by FGI gate).
        confluence_gate = _ANALYST_CONFLUENCE_ENTER
        if self._confluence_override is not None:
            override = self._confluence_override.get_confluence_override()
            if override is not None:
                confluence_gate = max(confluence_gate, override)

        if (
            not analyst_result.setup_valid
            or analyst_result.confluence_score < confluence_gate
        ):
            self._log_stop("Analyst", symbol, total_start)
            return PipelineResult(scout=scout_result, analyst=analyst_result)

        trader_run = await self._run_trader(
            symbol,
            deps_provider,
            analyst_result,
            scout_pattern=scout_result.pattern_detected,
        )
        if trader_run.decision is None:
            return PipelineResult(scout=scout_result, analyst=analyst_result)

        total_ms = (time.monotonic() - total_start) * 1000
        logger.info(
            "Agent pipeline completed for %s in %.1fms — reached tier trader",
            symbol,
            total_ms,
        )
        return PipelineResult(
            scout=scout_result,
            analyst=analyst_result,
            trader=trader_run.decision,
            trader_deps=trader_run.deps,
        )

    async def _fetch_scout_deps(
        self,
        symbol: str,
        deps_provider: DependenciesProvider,
    ) -> ScoutDependenciesSchema:
        return await deps_provider.get_scout(symbol)

    async def _invoke_scout(
        self,
        symbol: str,
        deps: ScoutDependenciesSchema,
    ) -> ScoutDecisionSchema | None:
        try:
            result = await self._scout.run(deps)
        except Exception:
            logger.exception("Scout agent failed for %s", symbol)
            return None
        return result

    async def _run_analyst(
        self,
        symbol: str,
        deps_provider: DependenciesProvider,
    ) -> AnalystDecisionSchema | None:
        deps = await deps_provider.get_analyst(symbol)
        self._log_analyst_inputs(deps)

        # Gate: skip the LLM call when algorithm confluence is too low.
        # The Analyst can add at most +3 points; if max algo < threshold,
        # even the maximum boost cannot reach the confluence entry gate.
        conf = deps.algorithm_confluence
        max_algo = max(conf.long.score, conf.short.score)
        if max_algo < self._analyst_min_algo_confluence:
            logger.info(
                "Analyst skipped for %s: max algorithm confluence %d < %d"
                " — insufficient for valid setup even with LLM bonus",
                symbol,
                max_algo,
                self._analyst_min_algo_confluence,
            )
            return AnalystDecisionSchema(
                setup_valid=False,
                direction="NEUTRAL",
                confluence_score=max_algo,
                key_levels=KeyLevelsSchema(levels=[]),
                reasoning=(
                    f"Analyst LLM call skipped: maximum algorithm"
                    f" confluence score {max_algo}/8 is below the"
                    f" minimum threshold"
                    f" {self._analyst_min_algo_confluence}. Even with"
                    f" the maximum analyst bonus of +3, the total cannot"
                    f" reach the confluence entry gate"
                    f" ({_ANALYST_CONFLUENCE_ENTER}) required to run"
                    f" the Trader tier."
                ),
            )

        # Gate 2: detected side has zero confluence — indicators likely stale.
        detected_score = (
            conf.long.score if conf.detected_side == "LONG" else conf.short.score
        )
        if detected_score == 0:
            logger.info(
                "Analyst skipped for %s: detected side %s has confluence"
                " 0/8 — indicators may be stale",
                symbol,
                conf.detected_side,
            )
            return AnalystDecisionSchema(
                setup_valid=False,
                direction="NEUTRAL",
                confluence_score=0,
                key_levels=KeyLevelsSchema(levels=[]),
                reasoning=(
                    f"Analyst LLM call skipped: detected side"
                    f" {conf.detected_side} has algorithm confluence"
                    f" 0/8, indicating all indicators returned False"
                    f" (possibly stale data)."
                ),
            )

        # Bar-close dedup: if the latest closed candle hasn't changed since
        # the previous Analyst call for this symbol, reuse the memoized
        # result. Skips redundant LLM calls inside the same 5-minute bar
        # when the ReasoningLoop cooldown expires mid-bar.
        current_bar = deps.recent_candles[-1].close_time
        prev_bar = self._last_analyzed_bar_close.get(symbol)
        if prev_bar is not None and current_bar == prev_bar:
            cached = self._last_analyst_result.get(symbol)
            if cached is not None:
                logger.info(
                    "Analyst dedup hit for %s: bar close_time=%s already"
                    " analyzed (cached conf=%d, valid=%s)",
                    symbol,
                    current_bar,
                    cached.confluence_score,
                    cached.setup_valid,
                )
                return cached

        try:
            result = await self._analyst.run(deps)
        except Exception:
            logger.exception("Analyst agent failed for %s", symbol)
            return None

        # Record the bar we just analyzed so subsequent cycles within the
        # same candle can short-circuit via the dedup hit above.
        self._last_analyzed_bar_close[symbol] = current_bar
        self._last_analyst_result[symbol] = result
        return result

    async def _run_trader(
        self,
        symbol: str,
        deps_provider: DependenciesProvider,
        analyst_result: AnalystDecisionSchema,
        scout_pattern: str | None = None,
    ) -> _TraderRunResult:
        deps = await deps_provider.get_trader(symbol)
        self._log_trader_inputs(deps, analyst_result, scout_pattern)

        # Deterministic pre-Trader gate: reject BREAKOUT at overextended %B
        breakout_reject = self._pre_trader_breakout_check(
            symbol,
            scout_pattern,
            deps,
        )
        if breakout_reject is not None:
            return _TraderRunResult(decision=breakout_reject, deps=deps)

        # Deterministic pre-Trader gate: reject poor estimated R/R
        rr_reject = self._pre_trader_rr_check(
            symbol,
            analyst_result,
            deps.current_price,
            deps.indicators.atr_14,
        )
        if rr_reject is not None:
            return _TraderRunResult(decision=rr_reject, deps=deps)

        t0 = time.monotonic()
        try:
            result = await self._trader.run(
                deps,
                analyst_result=analyst_result,
                scout_pattern=scout_pattern,
            )
        except (TimeoutError, httpx.TimeoutException):
            ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "Trader agent timed out for %s after %.1fs, returning WAIT",
                symbol,
                ms / 1000,
            )
            wait = TradeDecisionSchema(
                action="WAIT",
                confidence=0.0,
                reasoning=(
                    f"Trader agent timed out after {ms / 1000:.1f}s."
                    " Returning WAIT to avoid stale entry."
                    " Consider lowering trader timeout_s or using a"
                    " faster model."
                ),
                suggested_entry=None,
                suggested_stop_loss=None,
                suggested_take_profit=None,
            )
            return _TraderRunResult(decision=wait, deps=deps)
        except Exception:
            logger.exception("Trader agent failed for %s", symbol)
            return _TraderRunResult()
        return _TraderRunResult(decision=result, deps=deps)

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

    @staticmethod
    def _pre_trader_breakout_check(
        symbol: str,
        scout_pattern: str | None,
        deps: TradingDependenciesSchema,
    ) -> TradeDecisionSchema | None:
        """Reject BREAKOUT entries when %B indicates overextension."""
        if scout_pattern != "BREAKOUT":
            return None
        bb = deps.indicators.bollinger
        if bb is None:
            return None
        percent_b = bb.percent_b
        if percent_b > _BREAKOUT_OVEREXTENDED_B:
            logger.info(
                "Pre-Trader BREAKOUT reject for %s: %%B=%.2f > %.2f"
                " — price overextended beyond upper Bollinger Band",
                symbol,
                float(percent_b),
                float(_BREAKOUT_OVEREXTENDED_B),
            )
            return TradeDecisionSchema(
                action="WAIT",
                confidence=0.0,
                reasoning=(
                    f"Deterministic pre-Trader reject: BREAKOUT pattern with"
                    f" Bollinger %%B={float(percent_b):.2f} exceeds"
                    f" {float(_BREAKOUT_OVEREXTENDED_B):.2f} overextension"
                    f" threshold. Price is too far beyond the upper band for"
                    f" a sustainable breakout entry."
                ),
                suggested_entry=None,
                suggested_stop_loss=None,
                suggested_take_profit=None,
            )
        if percent_b > Decimal("1.10"):
            logger.warning(
                "BREAKOUT caution for %s: %%B=%.2f in 1.10-1.20 zone",
                symbol,
                float(percent_b),
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

    @staticmethod
    def _pre_trader_rr_check(
        symbol: str,
        analyst_result: AnalystDecisionSchema,
        current_price: Decimal,
        atr: Decimal | None,
    ) -> TradeDecisionSchema | None:
        """Reject when estimated R/R is below the pre-screen threshold."""
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
        if estimated_rr < _RR_MIN_PRESCREEN:
            logger.info(
                "Pre-Trader R/R reject for %s: estimated R/R=%.2f < %.1f",
                symbol,
                float(estimated_rr),
                float(_RR_MIN_PRESCREEN),
            )
            return TradeDecisionSchema(
                action="WAIT",
                confidence=0.0,
                reasoning=(
                    f"Deterministic pre-Trader reject: estimated"
                    f" risk/reward ratio {float(estimated_rr):.2f} is below"
                    f" the minimum pre-screen threshold of"
                    f" {float(_RR_MIN_PRESCREEN):.1f}. Key levels do not"
                    f" support a favorable entry at current price."
                ),
                suggested_entry=None,
                suggested_stop_loss=None,
                suggested_take_profit=None,
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
