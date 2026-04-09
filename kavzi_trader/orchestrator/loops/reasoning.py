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
    CONFLUENCE_ENTER_MIN,
    CONFLUENCE_REJECT_MAX,
)
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.filters.chain import PreTradeFilterChain
from kavzi_trader.spine.filters.filter_chain_result_schema import (
    FilterChainResultSchema,
)
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)

logger = logging.getLogger(__name__)

_BACKOFF_MULTIPLIER = 2.0
_MAX_BACKOFF_FACTOR = 6.0


# Cooldown (cycles) for borderline/LLM-reject bands. Short enough that the
# next bar-close will naturally retrigger the Analyst, but long enough to
# avoid tight retries within the same bar.
_BORDERLINE_COOLDOWN_CYCLES = 1

# Multipliers inside the aggressive rejection band (score <= 3).
_COOLDOWN_LOW_CONFLUENCE_THRESHOLD = 2  # score <= 2 → highest multiplier

_SKIP_SUSPENSION_THRESHOLD = 20
_MAX_SKIP_EVAL_INTERVAL = 16

_WAIT_COOLDOWN_THRESHOLD = 5
_WAIT_COOLDOWN_BASE_CYCLES = 2
_WAIT_MAX_COOLDOWN_CYCLES = 12


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
        self._cooldowns: dict[tuple[str, str], int] = {}  # (symbol, direction)
        self._consecutive_rejections: dict[tuple[str, str], int] = {}
        self._consecutive_waits: dict[tuple[str, str], int] = {}
        self._consecutive_skips: dict[str, int] = {}
        self._skip_eval_interval: dict[str, int] = {}

    async def run(self) -> None:
        logger.info(
            "ReasoningLoop started with %d symbols, interval=%ds",
            len(self._symbols),
            self._interval_s,
        )
        cycle = 0
        current_interval = float(self._interval_s)
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
            if interesting_count > 0:
                current_interval = float(self._interval_s)
            else:
                current_interval = min(
                    current_interval * _BACKOFF_MULTIPLIER,
                    self._interval_s * _MAX_BACKOFF_FACTOR,
                )
            cycle_ms = (time.monotonic() - cycle_start) * 1000
            logger.info(
                "ReasoningLoop cycle %d complete in %.1fms, "
                "interesting=%d/%d, sleeping %.0fs",
                cycle,
                cycle_ms,
                interesting_count,
                len(results),
                current_interval,
                extra={
                    "cycle": cycle,
                    "elapsed_ms": round(cycle_ms, 1),
                    "interesting_count": interesting_count,
                    "sleep_interval": round(current_interval, 1),
                },
            )
            await asyncio.sleep(current_interval)

    async def _fetch_cycle_positions(self) -> list[PositionSchema]:
        if self._state_manager is None:
            return []
        try:
            return await self._state_manager.get_all_positions()
        except Exception:
            logger.exception("Failed to fetch positions for reasoning cycle")
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
                extra={"symbol": symbol},
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
            if count >= _SKIP_SUSPENSION_THRESHOLD:
                new_interval = min(
                    max(self._skip_eval_interval.get(symbol, 1) * 2, 2),
                    _MAX_SKIP_EVAL_INTERVAL,
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
            )

        self._track_skip_suspension(symbol, result.scout.verdict)

        if result.analyst is not None:
            self._apply_analyst_cooldown(symbol, result.analyst)

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

    def _apply_analyst_cooldown(
        self,
        symbol: str,
        analyst: AnalystDecisionSchema,
    ) -> None:
        """Apply hysteresis-banded cooldown based on Analyst verdict.

        Three bands avoid flip-flopping at the old hard cutoff:
          * score <= 3 + invalid → escalating multiplier, counts toward
            _consecutive_rejections.
          * borderline (4-5) or LLM rejects high confluence (>=6 + invalid) →
            light single-cycle cooldown, no counter escalation. The next bar
            close naturally retriggers the Analyst.
          * valid setup at/above entry gate → clear lingering rejection counts.
        """
        score = analyst.confluence_score
        setup_valid = analyst.setup_valid
        direction = analyst.direction
        cooldown_dirs = ["LONG", "SHORT"] if direction == "NEUTRAL" else [direction]

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

        if not setup_valid or score < CONFLUENCE_ENTER_MIN:
            for d in cooldown_dirs:
                key = (symbol, d)
                existing = self._cooldowns.get(key, 0)
                self._cooldowns[key] = max(existing, _BORDERLINE_COOLDOWN_CYCLES)
            logger.debug(
                "Borderline analyst %s direction=%s score=%d setup_valid=%s"
                " → cooldown=%d (no escalation)",
                symbol,
                direction,
                score,
                setup_valid,
                _BORDERLINE_COOLDOWN_CYCLES,
            )
            return

        if direction == "NEUTRAL":
            self._consecutive_rejections.pop((symbol, "LONG"), None)
            self._consecutive_rejections.pop((symbol, "SHORT"), None)
        else:
            self._consecutive_rejections.pop((symbol, direction), None)

    def _compute_rejection_cooldown(self, confluence_score: int) -> int:
        """Scale rejection cooldown within the aggressive band (score <= 3)."""
        multiplier = 3 if confluence_score <= _COOLDOWN_LOW_CONFLUENCE_THRESHOLD else 2
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
            if count >= _WAIT_COOLDOWN_THRESHOLD:
                excess = count - _WAIT_COOLDOWN_THRESHOLD + 1
                cooldown = min(
                    _WAIT_COOLDOWN_BASE_CYCLES * excess,
                    _WAIT_MAX_COOLDOWN_CYCLES,
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
        if result.analyst.confluence_score < CONFLUENCE_ENTER_MIN:
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
        try:
            await self._redis_client.client.lpush(
                self._queue_key,
                decision.model_dump_json(),
            )
        except Exception:
            logger.exception(
                "Failed to enqueue decision for %s",
                symbol,
                extra={"symbol": symbol},
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
    ) -> DecisionMessageSchema:
        decision_id = str(uuid4())
        position_management = PositionManagementConfigSchema()

        entry_price = trader.suggested_entry or deps.current_price
        stop_loss = trader.suggested_stop_loss or entry_price
        take_profit = trader.suggested_take_profit or entry_price
        atr = deps.indicators.atr_14 or Decimal(0)
        if trader.action not in {"LONG", "SHORT", "CLOSE"}:
            raise ValueError("Unsupported action for execution queue")
        action = cast("Literal['LONG', 'SHORT', 'CLOSE']", trader.action)

        return DecisionMessageSchema(
            decision_id=decision_id,
            symbol=deps.symbol,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=Decimal(0),
            reasoning=trader.reasoning,
            raw_confidence=trader.confidence,
            calibrated_confidence=trader.confidence,
            volatility_regime=deps.volatility_regime,
            position_management=position_management,
            created_at_ms=snapshot_at_ms,
            expires_at_ms=snapshot_at_ms + 300_000,
            current_atr=atr,
            atr_history=deps.atr_history,
            leverage=deps.leverage,
            symbol_tier=deps.symbol_tier,
        )
