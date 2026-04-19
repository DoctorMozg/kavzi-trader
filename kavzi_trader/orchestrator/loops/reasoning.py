from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import uuid4

from kavzi_trader.brain.agent.router import (
    AgentRouter,
    DependenciesProvider,
    PipelineResult,
)
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.orchestrator.loops.confluence_thresholds import (
    CONFLUENCE_REJECT_MAX,
    confluence_enter_min_for_regime,
)
from kavzi_trader.orchestrator.loops.reasoning_config import (
    ReasoningLoopConfigSchema,
)
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.filters.chain import PreTradeFilterChain
from kavzi_trader.spine.filters.filter_chain_result_schema import (
    FilterChainResultSchema,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)

logger = logging.getLogger(__name__)


class ReasoningLoop:
    """Runs the agent router and enqueues trade decisions."""

    def __init__(
        self,
        symbols: list[str],
        router: AgentRouter,
        deps_provider: DependenciesProvider,
        redis_client: RedisStateClient,
        queue_key: str = "kt:decisions:pending",
        interval_s: int = 5,
        report_populator: TradeReportPopulator | None = None,
        state_manager: StateManager | None = None,
        analyst_cooldown_cycles: int = 3,
        filter_chain: PreTradeFilterChain | None = None,
        max_consecutive_rejection_multiplier: int = 3,
        *,
        reasoning_config: ReasoningLoopConfigSchema | None = None,
    ) -> None:
        self._symbols = symbols
        self._router = router
        self._deps_provider = deps_provider
        self._redis_client = redis_client
        self._queue_key = queue_key
        self._interval_s = interval_s
        self._report_populator = report_populator
        self._state_manager = state_manager
        self._analyst_cooldown_cycles = analyst_cooldown_cycles
        self._filter_chain = filter_chain
        self._max_rejection_multiplier = max_consecutive_rejection_multiplier
        self._reasoning_config = reasoning_config or ReasoningLoopConfigSchema()
        self._cooldowns: dict[tuple[str, str], int] = {}  # (symbol, direction)
        self._consecutive_rejections: dict[tuple[str, str], int] = {}
        self._consecutive_waits: dict[tuple[str, str], int] = {}
        self._consecutive_skips: dict[str, int] = {}
        self._skip_eval_interval: dict[str, int] = {}
        # Tracks the number of consecutive cycles that produced zero
        # INTERESTING scouts. Drives the progressive idle sleep ramp; any
        # INTERESTING cycle resets the counter.
        self._consecutive_idle_cycles: int = 0

    async def run(self) -> None:
        logger.info(
            "ReasoningLoop started with %d symbols, interval=%ds",
            len(self._symbols),
            self._interval_s,
        )
        cycle = 0
        current_interval_s = float(self._interval_s)
        while True:
            cycle += 1
            cycle_start = time.monotonic()
            logger.debug("ReasoningLoop cycle %d starting", cycle)
            self._deps_provider.clear_cycle_cache()
            cached_positions = await self._fetch_cycle_positions()
            results: list[bool] = await asyncio.gather(
                *(
                    self._handle_symbol_timed(symbol, cached_positions)
                    for symbol in self._symbols
                ),
            )
            interesting_count = sum(results)
            current_interval_s = self._next_sleep_interval_s(interesting_count)
            cycle_ms = (time.monotonic() - cycle_start) * 1000
            logger.info(
                "ReasoningLoop cycle %d complete in %.1fms, "
                "interesting=%d/%d, sleeping %.0fs",
                cycle,
                cycle_ms,
                interesting_count,
                len(results),
                current_interval_s,
                extra={
                    "cycle": cycle,
                    "elapsed_ms": round(cycle_ms, 1),
                    "interesting_count": interesting_count,
                    "sleep_interval_s": round(current_interval_s, 1),
                    "consecutive_idle_cycles": self._consecutive_idle_cycles,
                },
            )
            await asyncio.sleep(current_interval_s)

    def _next_sleep_interval_s(self, interesting_count: int) -> float:
        """Return the sleep interval for the next cycle.

        Resets to the base interval whenever any symbol was INTERESTING.
        On idle cycles, advances ``_consecutive_idle_cycles`` and walks the
        idle-ramp stairs, picking the deepest matching stair.
        """
        if interesting_count > 0:
            self._consecutive_idle_cycles = 0
            return float(self._interval_s)
        self._consecutive_idle_cycles += 1
        for stair in self._reasoning_config.idle_ramp_stairs:
            if self._consecutive_idle_cycles >= stair.min_idle_cycles:
                return float(stair.sleep_s)
        return float(self._interval_s)

    async def _fetch_cycle_positions(self) -> list[PositionSchema]:
        if self._state_manager is None:
            return []
        try:
            return await self._state_manager.get_all_positions()
        except Exception:
            logger.exception(
                "Failed to fetch positions for reasoning cycle",
                extra={"loop": "reasoning"},
            )
            return []

    async def _handle_symbol_timed(
        self,
        symbol: str,
        cached_positions: list[PositionSchema],
    ) -> bool:
        sym_start = time.monotonic()
        interesting = False
        try:
            interesting = await self._handle_symbol(symbol, cached_positions)
        except Exception:
            logger.exception(
                "ReasoningLoop failed for %s, continuing",
                symbol,
                extra={"loop": "reasoning", "symbol": symbol},
            )
        sym_ms = (time.monotonic() - sym_start) * 1000
        logger.info(
            "ReasoningLoop symbol=%s elapsed_ms=%.1f",
            symbol,
            sym_ms,
            extra={"symbol": symbol, "elapsed_ms": round(sym_ms, 1)},
        )
        return interesting

    def _get_open_position_symbols(
        self,
        cached_positions: list[PositionSchema],
    ) -> set[str]:
        return {p.symbol for p in cached_positions}

    def _is_suspended(self, symbol: str) -> bool:
        """Check if a symbol is dynamically suspended due to consecutive SKIPs."""
        skip_interval = self._skip_eval_interval.get(symbol, 0)
        if skip_interval <= 0:
            return False
        skip_count = self._consecutive_skips.get(symbol, 0)
        if skip_count % skip_interval != 0:
            self._consecutive_skips[symbol] = skip_count + 1
            return True
        return False

    def _track_skip_suspension(self, symbol: str, verdict: str) -> None:
        """Update dynamic suspension state based on scout verdict."""
        if verdict == "SKIP":
            count = self._consecutive_skips.get(symbol, 0) + 1
            self._consecutive_skips[symbol] = count
            if count >= self._reasoning_config.skip_suspension_threshold:
                new_interval = min(
                    max(self._skip_eval_interval.get(symbol, 1) * 2, 2),
                    self._reasoning_config.max_skip_eval_interval,
                )
                self._skip_eval_interval[symbol] = new_interval
                logger.info(
                    "Symbol %s suspended: %d consecutive SKIPs, eval every %d cycles",
                    symbol,
                    count,
                    new_interval,
                    extra={"symbol": symbol},
                )
        else:
            self._consecutive_skips.pop(symbol, None)
            self._skip_eval_interval.pop(symbol, None)

    def _tick_cooldowns(self, symbol: str) -> bool:
        """Decrement direction cooldowns. Return True if ALL directions are blocked."""
        long_cd = self._cooldowns.get((symbol, "LONG"), 0)
        short_cd = self._cooldowns.get((symbol, "SHORT"), 0)

        if long_cd > 0:
            self._cooldowns[(symbol, "LONG")] = long_cd - 1
        if short_cd > 0:
            self._cooldowns[(symbol, "SHORT")] = short_cd - 1

        # Only skip when both directions are on cooldown
        return long_cd > 0 and short_cd > 0

    def _should_skip_symbol(
        self,
        symbol: str,
        cached_positions: list[PositionSchema],
    ) -> bool:
        if self._tick_cooldowns(symbol):
            return True
        if self._is_suspended(symbol):
            return True
        if not self._deps_provider.indicators_available(symbol):
            return True
        open_symbols = self._get_open_position_symbols(cached_positions)
        return symbol in open_symbols

    async def _handle_symbol(
        self,
        symbol: str,
        cached_positions: list[PositionSchema],
    ) -> bool:
        if self._should_skip_symbol(symbol, cached_positions):
            return False

        result = await self._router.run(symbol, self._deps_provider)
        try:
            await self._report_decisions(
                symbol,
                result.scout,
                result.analyst,
                result.trader,
            )
        except Exception:
            logger.exception(
                "Failed to report decisions for %s",
                symbol,
                extra={
                    "loop": "reasoning",
                    "symbol": symbol,
                    "scout_verdict": result.scout.verdict,
                },
            )

        self._track_skip_suspension(symbol, result.scout.verdict)

        if result.analyst is not None:
            self._apply_analyst_cooldown(
                symbol,
                result.analyst,
                self._regime_of(result),
            )

        if not self._should_enqueue(result):
            self._track_consecutive_waits(symbol, result)
            return result.scout.verdict == "INTERESTING"

        filter_result = await self._run_filter_chain(result, cached_positions)
        if filter_result is not None and not filter_result.is_allowed:
            await self._report_filter_rejection(
                symbol,
                result.trader.action if result.trader else "UNKNOWN",
                filter_result,
            )
            return True

        # After trade enqueue, cool down both directions and reset WAIT counters
        post_trade_cd = self._analyst_cooldown_cycles * 3
        self._cooldowns[(symbol, "LONG")] = post_trade_cd
        self._cooldowns[(symbol, "SHORT")] = post_trade_cd
        self._consecutive_waits.pop((symbol, "LONG"), None)
        self._consecutive_waits.pop((symbol, "SHORT"), None)
        await self._enqueue_decision(result)
        return True

    @staticmethod
    def _regime_of(result: PipelineResult) -> VolatilityRegime:
        """Return the volatility regime associated with a pipeline result.

        Falls back to NORMAL when ``trader_deps`` is absent (e.g. Scout
        SKIP or Analyst rejection before Trader deps are built) so cooldown
        logic has a deterministic default rather than silently using the
        wrong regime's gate.
        """
        if result.trader_deps is None:
            return VolatilityRegime.NORMAL
        return result.trader_deps.volatility_regime

    def _apply_analyst_cooldown(
        self,
        symbol: str,
        analyst: AnalystDecisionSchema,
        volatility_regime: VolatilityRegime,
    ) -> None:
        """Apply hysteresis-banded cooldown based on Analyst verdict.

        Three bands avoid flip-flopping at the old hard cutoff:
          * score <= 3 + invalid → escalating multiplier, counts toward
            _consecutive_rejections.
          * borderline (4-5) or LLM rejects high confluence (>=6 + invalid) →
            light single-cycle cooldown, no counter escalation. The next bar
            close naturally retriggers the Analyst.
          * valid setup at/above entry gate → clear lingering rejection counts.

        The "borderline vs valid" boundary is the regime-specific entry
        gate. NORMAL regimes keep the historical 6-point cutoff; HIGH and
        EXTREME widen the borderline band so a score of 6 under HIGH is
        treated as borderline instead of enqueable.
        """
        score = analyst.confluence_score
        setup_valid = analyst.setup_valid
        direction = analyst.direction
        cooldown_dirs = ["LONG", "SHORT"] if direction == "NEUTRAL" else [direction]
        regime_gate = confluence_enter_min_for_regime(volatility_regime)

        if not setup_valid and score <= CONFLUENCE_REJECT_MAX:
            for d in cooldown_dirs:
                key = (symbol, d)
                count = self._consecutive_rejections.get(key, 0) + 1
                self._consecutive_rejections[key] = count
                base_cooldown = self._compute_rejection_cooldown(score)
                multiplier = min(count, self._max_rejection_multiplier)
                self._cooldowns[key] = base_cooldown * multiplier
                logger.debug(
                    "Consecutive rejection %d for %s %s: cooldown=%d (base=%d x %d)",
                    count,
                    symbol,
                    d,
                    base_cooldown * multiplier,
                    base_cooldown,
                    multiplier,
                )
            return

        if not setup_valid or score < regime_gate:
            for d in cooldown_dirs:
                key = (symbol, d)
                existing = self._cooldowns.get(key, 0)
                self._cooldowns[key] = max(
                    existing,
                    self._reasoning_config.borderline_cooldown_cycles,
                )
            logger.debug(
                "Borderline analyst %s direction=%s score=%d setup_valid=%s"
                " regime=%s gate=%d → cooldown=%d (no escalation)",
                symbol,
                direction,
                score,
                setup_valid,
                volatility_regime.value,
                regime_gate,
                self._reasoning_config.borderline_cooldown_cycles,
            )
            return

        if direction == "NEUTRAL":
            self._consecutive_rejections.pop((symbol, "LONG"), None)
            self._consecutive_rejections.pop((symbol, "SHORT"), None)
        else:
            self._consecutive_rejections.pop((symbol, direction), None)

    def _compute_rejection_cooldown(self, confluence_score: int) -> int:
        """Scale rejection cooldown within the aggressive band (score <= 3)."""
        low_band = self._reasoning_config.cooldown_low_confluence_threshold
        multiplier = 3 if confluence_score <= low_band else 2
        cooldown = self._analyst_cooldown_cycles * multiplier
        logger.debug(
            "Rejection cooldown: confluence=%d multiplier=%d cooldown=%d cycles",
            confluence_score,
            multiplier,
            cooldown,
        )
        return cooldown

    def _track_consecutive_waits(
        self,
        symbol: str,
        result: PipelineResult,
    ) -> None:
        """Apply escalating cooldown after repeated Trader WAITs."""
        if result.trader is None or result.trader.action != "WAIT":
            return
        direction = (
            result.analyst.direction if result.analyst is not None else "NEUTRAL"
        )
        wait_dirs = ["LONG", "SHORT"] if direction == "NEUTRAL" else [direction]
        for d in wait_dirs:
            key = (symbol, d)
            count = self._consecutive_waits.get(key, 0) + 1
            self._consecutive_waits[key] = count
            wait_threshold = self._reasoning_config.wait_cooldown_threshold
            if count >= wait_threshold:
                excess = count - wait_threshold + 1
                cooldown = min(
                    self._reasoning_config.wait_cooldown_base_cycles * excess,
                    self._reasoning_config.wait_max_cooldown_cycles,
                )
                self._cooldowns[key] = cooldown
                logger.info(
                    "Consecutive WAIT %d for %s %s: cooldown=%d cycles",
                    count,
                    symbol,
                    d,
                    cooldown,
                )

    def _should_enqueue(self, result: PipelineResult) -> bool:
        if result.scout.verdict != "INTERESTING":
            return False
        if result.analyst is None or not result.analyst.setup_valid:
            return False
        regime_gate = confluence_enter_min_for_regime(self._regime_of(result))
        if result.analyst.confluence_score < regime_gate:
            return False
        if result.trader is None:
            return False
        return result.trader.action in {"LONG", "SHORT", "CLOSE"}

    async def _run_filter_chain(
        self,
        result: PipelineResult,
        cached_positions: list[PositionSchema],
    ) -> FilterChainResultSchema | None:
        if (
            self._filter_chain is None
            or result.trader is None
            or result.trader_deps is None
        ):
            return None
        if result.trader.action not in {"LONG", "SHORT"}:
            return None
        deps = result.trader_deps
        confluence_score = (
            result.analyst.confluence_score if result.analyst is not None else None
        )
        return await self._filter_chain.evaluate(
            symbol=deps.symbol,
            side=cast("Literal['LONG', 'SHORT']", result.trader.action),
            candle=deps.recent_candles[-1],
            indicators=deps.indicators,
            order_flow=deps.order_flow,
            positions=cached_positions,
            atr_history=deps.atr_history,
            analyst_confluence_score=confluence_score,
            symbol_tier=deps.symbol_tier,
        )

    async def _report_filter_rejection(
        self,
        symbol: str,
        action: str,
        filter_result: FilterChainResultSchema,
    ) -> None:
        logger.info(
            "Filter chain REJECTED %s %s: %s",
            symbol,
            action,
            filter_result.rejection_reason,
            extra={"symbol": symbol, "action": action},
        )
        if self._report_populator is not None:
            failed = [r.name for r in filter_result.results if not r.is_allowed]
            await self._report_populator.record_action(
                action_type="filter_rejection",
                symbol=symbol,
                summary=f"Blocked {action}: {filter_result.rejection_reason}",
                details=f"Failed filters: {', '.join(failed)}",
            )

    async def _enqueue_decision(
        self,
        result: PipelineResult,
    ) -> None:
        if result.trader is None or result.trader_deps is None:
            return
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        decision = self._build_decision_message(
            result.trader,
            result.trader_deps,
            now_ms,
        )
        symbol = result.trader_deps.symbol
        if decision is None:
            logger.warning(
                "Skipping enqueue for %s: decision message could not be"
                " built from Trader output (see prior error log)",
                symbol,
                extra={"symbol": symbol},
            )
            return
        try:
            await self._redis_client.client.lpush(
                self._queue_key,
                decision.model_dump_json(),
            )
        except Exception:
            logger.exception(
                "Failed to enqueue decision for %s",
                symbol,
                extra={
                    "loop": "reasoning",
                    "symbol": symbol,
                    "decision_id": decision.decision_id,
                    "action": decision.action,
                    "queue_key": self._queue_key,
                },
            )
            return
        logger.info(
            "Enqueuing decision for %s: action=%s confidence=%.2f decision_id=%s",
            symbol,
            decision.action,
            decision.raw_confidence,
            decision.decision_id,
            extra={
                "symbol": symbol,
                "decision_id": decision.decision_id,
                "action": decision.action,
            },
        )

    async def _report_decisions(
        self,
        symbol: str,
        scout: ScoutDecisionSchema,
        analyst: AnalystDecisionSchema | None,
        trader: TradeDecisionSchema | None,
    ) -> None:
        if self._report_populator is None:
            return
        await self._report_populator.record_action(
            action_type="scout_scan",
            symbol=symbol,
            summary=f"Verdict: {scout.verdict} — {scout.reason}",
            details=scout.pattern_detected,
        )
        if analyst is not None:
            await self._report_populator.record_action(
                action_type="analyst_review",
                symbol=symbol,
                summary=(
                    f"Valid: {analyst.setup_valid}, Direction: {analyst.direction}, "
                    f"Confluence: {analyst.confluence_score}/11"
                ),
                details=analyst.reasoning,
            )
        if trader is not None:
            await self._report_populator.record_action(
                action_type="trader_decision",
                symbol=symbol,
                summary=(
                    f"Action: {trader.action}, "
                    f"Confidence: {trader.confidence * 100:.0f}%"
                ),
                details=trader.reasoning,
            )
        if analyst is not None and trader is not None:
            await self._report_populator.record_action(
                action_type="pipeline_complete",
                symbol=symbol,
                summary=(
                    f"Scout={scout.verdict} "
                    f"Analyst={analyst.direction}"
                    f"(conf={analyst.confluence_score}) "
                    f"Trader={trader.action}"
                    f"(conf={trader.confidence * 100:.0f}%)"
                ),
                details=None,
            )

    def _build_decision_message(
        self,
        trader: TradeDecisionSchema,
        deps: TradingDependenciesSchema,
        snapshot_at_ms: int,
    ) -> DecisionMessageSchema | None:
        # Reject malformed Trader output at the Brain→Spine boundary. LONG
        # and SHORT must carry full trade geometry; silently substituting
        # entry_price for missing stop_loss/take_profit would construct a
        # self-closing trade that the schema validator still accepts as
        # geometry-skipped CLOSE-equivalent. Fail loud and increment the
        # Trader circuit-breaker counter so repeated malformed output
        # suspends the symbol.
        action = trader.action
        if action in {"LONG", "SHORT"}:
            missing: list[str] = []
            if trader.suggested_entry is None:
                missing.append("suggested_entry")
            if trader.suggested_stop_loss is None:
                missing.append("suggested_stop_loss")
            if trader.suggested_take_profit is None:
                missing.append("suggested_take_profit")
            if missing:
                logger.error(
                    "Trader %s decision for %s missing required fields: %s",
                    action,
                    deps.symbol,
                    missing,
                    extra={
                        "symbol": deps.symbol,
                        "action": action,
                        "missing_fields": missing,
                    },
                )
                self._router.record_trader_validation_failure(deps.symbol)
                return None

        # Only LONG/SHORT/CLOSE should reach this method — WAIT is filtered
        # by _should_enqueue upstream. A narrow cast satisfies mypy without
        # an unreachable defensive raise.
        typed_action = cast("Literal['LONG', 'SHORT', 'CLOSE']", action)

        # For CLOSE-only decisions the Trader may omit suggested prices;
        # geometry validation is skipped, so fall back to current price so
        # the schema can still be constructed.
        entry_price = trader.suggested_entry or deps.current_price
        stop_loss = trader.suggested_stop_loss or entry_price
        take_profit = trader.suggested_take_profit or entry_price
        atr = deps.indicators.atr_14 or Decimal(0)

        return DecisionMessageSchema(
            decision_id=str(uuid4()),
            symbol=deps.symbol,
            action=typed_action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=None,
            reasoning=trader.reasoning,
            raw_confidence=trader.confidence,
            calibrated_confidence=trader.confidence,
            volatility_regime=deps.volatility_regime,
            position_management=PositionManagementConfigSchema(),
            created_at_ms=snapshot_at_ms,
            expires_at_ms=snapshot_at_ms + 300_000,
            current_atr=atr,
            atr_history=deps.atr_history,
            leverage=deps.leverage,
            symbol_tier=deps.symbol_tier,
        )
