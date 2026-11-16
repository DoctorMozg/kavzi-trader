from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal

from kavzi_trader.brain.agent.router import (
    AgentRouter,
    DependenciesProvider,
    PipelineResult,
)
from kavzi_trader.commons.clock import Clock
from kavzi_trader.commons.system_clock import SYSTEM_CLOCK
from kavzi_trader.domain.state_schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)
from kavzi_trader.orchestrator.loops.cooldown_policy import CooldownPolicy
from kavzi_trader.orchestrator.loops.decision_message_builder import (
    DecisionMessageBuilder,
)
from kavzi_trader.orchestrator.loops.reasoning_config import (
    ReasoningLoopConfigSchema,
)
from kavzi_trader.orchestrator.loops.symbol_state import SymbolStateTracker
from kavzi_trader.spine.filters.chain import PreTradeFilterChain
from kavzi_trader.spine.filters.filter_chain_params_schema import (
    FilterChainParamsSchema,
)
from kavzi_trader.spine.filters.filter_chain_result_schema import (
    FilterChainResultSchema,
)
from kavzi_trader.strategies.bracket_intent_schema import BracketIntentSchema
from kavzi_trader.strategies.strategy_intent import StrategyIntent
from kavzi_trader.strategies.symbol_outcome_schema import SymbolOutcomeSchema
from kavzi_trader.strategies.tick_result_schema import StrategyTickResultSchema
from kavzi_trader.strategies.tick_schema import StrategyTickSchema
from kavzi_trader.ui.recorder import UiEventRecorder

logger = logging.getLogger(__name__)


class LlmPipelinePlugin:
    """Scout -> Analyst -> Trader pipeline exposed as a strategy plugin."""

    name = "llm_pipeline"

    def __init__(
        self,
        symbols: list[str],
        router: AgentRouter,
        deps_provider: DependenciesProvider,
        interval_s: int = 5,
        ui_recorder: UiEventRecorder | None = None,
        analyst_cooldown_cycles: int = 3,
        filter_chain: PreTradeFilterChain | None = None,
        max_consecutive_rejection_multiplier: int = 3,
        *,
        position_management: PositionManagementConfigSchema,
        reasoning_config: ReasoningLoopConfigSchema | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._symbols = symbols
        self._router = router
        self._deps_provider = deps_provider
        self._interval_s = interval_s
        self._ui_recorder = ui_recorder
        self._clock = clock
        self._filter_chain = filter_chain
        self._reasoning_config = reasoning_config or ReasoningLoopConfigSchema()
        self._state = SymbolStateTracker()
        self._cooldowns = CooldownPolicy(
            self._state,
            self._reasoning_config,
            analyst_cooldown_cycles,
            max_consecutive_rejection_multiplier,
        )
        self._builder = DecisionMessageBuilder(
            position_management,
            router.record_trader_validation_failure,
        )
        # Tracks the number of consecutive cycles that produced zero
        # INTERESTING scouts. Drives the progressive idle sleep ramp; any
        # INTERESTING cycle resets the counter.
        self._consecutive_idle_cycles: int = 0
        # Tracks the idle-ramp stair index for transition-based logging.
        # ``None`` indicates active mode (not currently ramped into idle).
        # Only transitions (active→idle, stair advances, idle→active) log;
        # steady-state idle cycles stay silent to reduce log noise.
        self._last_idle_stair_index: int | None = None
        self._cycle: int = 0

    async def tick(self, ctx: StrategyTickSchema) -> StrategyTickResultSchema:
        self._cycle += 1
        cycle = self._cycle
        cycle_start = time.monotonic()
        logger.debug("LlmPipelinePlugin cycle %d starting", cycle)
        self._deps_provider.clear_cycle_cache()
        raw_results: list[SymbolOutcomeSchema | BaseException] = await asyncio.gather(
            *(
                self._handle_symbol_timed(symbol, ctx.positions)
                for symbol in self._symbols
            ),
            return_exceptions=True,
        )
        outcomes: list[SymbolOutcomeSchema] = []
        for symbol, result in zip(self._symbols, raw_results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "LlmPipelinePlugin symbol %s raised, treating as non-interesting",
                    symbol,
                    exc_info=result,
                    extra={
                        "loop": "reasoning",
                        "symbol": symbol,
                        "cycle": cycle,
                    },
                )
                outcomes.append(SymbolOutcomeSchema(interesting=False))
                continue
            outcomes.append(result)
        interesting_count = sum(o.interesting for o in outcomes)
        sleep_s, stair_index = self._next_sleep_interval_s(interesting_count)
        cycle_ms = (time.monotonic() - cycle_start) * 1000
        if stair_index != self._last_idle_stair_index:
            logger.info(
                "LlmPipelinePlugin cycle %d complete in %.1fms, "
                "interesting=%d/%d, sleeping %.0fs",
                cycle,
                cycle_ms,
                interesting_count,
                len(outcomes),
                sleep_s,
                extra={
                    "cycle": cycle,
                    "elapsed_ms": round(cycle_ms, 1),
                    "interesting_count": interesting_count,
                    "sleep_interval_s": round(sleep_s, 1),
                    "consecutive_idle_cycles": self._consecutive_idle_cycles,
                    "idle_stair_index": stair_index,
                    "previous_idle_stair_index": self._last_idle_stair_index,
                },
            )
            self._last_idle_stair_index = stair_index
        else:
            logger.debug(
                "LlmPipelinePlugin cycle %d complete in %.1fms, "
                "interesting=%d/%d, sleeping %.0fs",
                cycle,
                cycle_ms,
                interesting_count,
                len(outcomes),
                sleep_s,
            )
        return StrategyTickResultSchema(
            intents=[o.intent for o in outcomes if o.intent is not None],
            next_tick_at_ms=self._clock.now_ms() + round(sleep_s * 1000),
        )

    def on_enqueued(self, intent: StrategyIntent) -> None:
        self._cooldowns.start_post_trade_cooldown(intent.symbol)

    def _next_sleep_interval_s(
        self, interesting_count: int
    ) -> tuple[float, int | None]:
        """Return the sleep interval and idle-stair index for the next cycle.

        The stair index is ``None`` in active mode (any INTERESTING symbol
        this cycle) or when idle cycles haven't yet crossed the first stair
        threshold; otherwise it is the index into
        ``idle_ramp_stairs`` that dictated the sleep. The index is used by
        the run loop to log only on idle-ramp state transitions.

        Resets to the base interval whenever any symbol was INTERESTING.
        On idle cycles, advances ``_consecutive_idle_cycles`` and walks the
        idle-ramp stairs, picking the deepest matching stair.
        """
        if interesting_count > 0:
            self._consecutive_idle_cycles = 0
            return float(self._interval_s), None
        self._consecutive_idle_cycles += 1
        for index, stair in enumerate(self._reasoning_config.idle_ramp_stairs):
            if self._consecutive_idle_cycles >= stair.min_idle_cycles:
                capped = min(stair.sleep_s, self._reasoning_config.max_idle_sleep_s)
                return float(capped), index
        return float(self._interval_s), None

    async def _handle_symbol_timed(
        self,
        symbol: str,
        cached_positions: list[PositionSchema],
    ) -> SymbolOutcomeSchema:
        sym_start = time.monotonic()
        outcome = SymbolOutcomeSchema(interesting=False)
        try:
            outcome = await self._handle_symbol(symbol, cached_positions)
        except Exception:
            logger.exception(
                "LlmPipelinePlugin failed for %s, continuing",
                symbol,
                extra={"loop": "reasoning", "symbol": symbol},
            )
        sym_ms = (time.monotonic() - sym_start) * 1000
        logger.info(
            "LlmPipelinePlugin symbol=%s elapsed_ms=%.1f",
            symbol,
            sym_ms,
            extra={"symbol": symbol, "elapsed_ms": round(sym_ms, 1)},
        )
        return outcome

    def _get_open_position_symbols(
        self,
        cached_positions: list[PositionSchema],
    ) -> set[str]:
        return {p.symbol for p in cached_positions}

    def _should_skip_symbol(
        self,
        symbol: str,
        cached_positions: list[PositionSchema],
    ) -> bool:
        if self._cooldowns.tick(symbol):
            return True
        if self._cooldowns.is_suspended(symbol):
            return True
        if not self._deps_provider.indicators_available(symbol):
            return True
        open_symbols = self._get_open_position_symbols(cached_positions)
        return symbol in open_symbols

    async def _handle_symbol(
        self,
        symbol: str,
        cached_positions: list[PositionSchema],
    ) -> SymbolOutcomeSchema:
        if self._should_skip_symbol(symbol, cached_positions):
            return SymbolOutcomeSchema(interesting=False)

        pipeline_start_s = time.monotonic()
        result = await self._router.run(symbol, self._deps_provider)
        pipeline_ms = round((time.monotonic() - pipeline_start_s) * 1000)
        try:
            await self._report_decisions(symbol, result, pipeline_ms)
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

        self._cooldowns.track_skip_suspension(symbol, result.scout.verdict)

        # PipelineResult guarantees gates whenever an Analyst decision exists.
        if result.analyst is not None and result.gates is not None:
            self._cooldowns.apply_analyst_cooldown(
                symbol,
                result.analyst,
                result.gates,
            )

        self._cooldowns.track_geometry_rejects(symbol, result)

        if not self._should_enqueue(result):
            self._cooldowns.track_consecutive_waits(symbol, result)
            return SymbolOutcomeSchema(
                interesting=result.scout.verdict == "INTERESTING"
            )

        filter_result = await self._run_filter_chain(result, cached_positions)
        if filter_result is not None and not filter_result.is_allowed:
            await self._report_filter_rejection(
                symbol,
                result.trader.action if result.trader else "UNKNOWN",
                filter_result,
            )
            return SymbolOutcomeSchema(interesting=True)

        size_multiplier = (
            filter_result.size_multiplier if filter_result is not None else Decimal(1)
        )
        # A missing intent means nothing goes out, so the symbol stays eligible.
        return SymbolOutcomeSchema(
            interesting=True,
            intent=self._build_intent(result, size_multiplier),
        )

    def _build_intent(
        self,
        result: PipelineResult,
        size_multiplier: Decimal,
    ) -> BracketIntentSchema | None:
        if result.trader is None or result.trader_deps is None:
            return None
        intent = self._builder.build(
            result.trader,
            result.trader_deps,
            self._clock.now_ms(),
            geometry=result.geometry,
            size_multiplier=size_multiplier,
        )
        if intent is None:
            logger.warning(
                "Skipping enqueue for %s: decision message could not be"
                " built from Trader output (see prior error log)",
                result.trader_deps.symbol,
                extra={"symbol": result.trader_deps.symbol},
            )
        return intent

    def _should_enqueue(self, result: PipelineResult) -> bool:
        if result.scout.verdict != "INTERESTING":
            return False
        if result.analyst is None or not result.analyst.setup_valid:
            return False
        if result.gates is None:
            return False
        if result.analyst.confluence_score < result.gates.regime_gate:
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
            or result.gates is None
        ):
            return None
        if result.trader.action not in {"LONG", "SHORT"}:
            return None
        deps = result.trader_deps
        confluence_score = (
            result.analyst.confluence_score if result.analyst is not None else None
        )
        params = FilterChainParamsSchema.model_validate(
            {
                "symbol": deps.symbol,
                "side": result.trader.action,
                "candle": deps.recent_candles[-1],
                "indicators": deps.indicators,
                "order_flow": deps.order_flow,
                "positions": cached_positions,
                "atr_history": deps.atr_history,
                "analyst_confluence_score": confluence_score,
                "confluence_threshold_shift": result.gates.threshold_shift,
                "symbol_tier": deps.symbol_tier,
                "confidence": Decimal(str(result.trader.confidence)),
            },
        )
        return await self._filter_chain.evaluate(params)

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
        if self._ui_recorder is not None:
            await self._ui_recorder.record_filter_rejection(
                symbol,
                action,
                filter_result.rejection_reason or "unknown",
                [r.name for r in filter_result.results if not r.is_allowed],
            )

    async def _report_decisions(
        self,
        symbol: str,
        result: PipelineResult,
        pipeline_ms: int,
    ) -> None:
        if self._ui_recorder is None:
            return
        await self._ui_recorder.record_pipeline(
            symbol,
            result.scout,
            result.analyst,
            result.trader,
            pipeline_ms,
        )
