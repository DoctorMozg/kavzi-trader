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
from kavzi_trader.domain.state_schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.orchestrator.loops.cooldown_policy import CooldownPolicy
from kavzi_trader.orchestrator.loops.decision_message_builder import (
    DecisionMessageBuilder,
)
from kavzi_trader.orchestrator.loops.decision_publisher import DecisionPublisher
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
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.ui.recorder import UiEventRecorder

logger = logging.getLogger(__name__)


class ReasoningLoop:
    """Runs the agent router and enqueues trade decisions."""

    def __init__(
        self,
        symbols: list[str],
        router: AgentRouter,
        deps_provider: DependenciesProvider,
        redis_client: RedisStateClient,
        interval_s: int = 5,
        ui_recorder: UiEventRecorder | None = None,
        state_manager: StateManager | None = None,
        analyst_cooldown_cycles: int = 3,
        filter_chain: PreTradeFilterChain | None = None,
        max_consecutive_rejection_multiplier: int = 3,
        *,
        position_management: PositionManagementConfigSchema,
        reasoning_config: ReasoningLoopConfigSchema | None = None,
    ) -> None:
        self._symbols = symbols
        self._router = router
        self._deps_provider = deps_provider
        self._interval_s = interval_s
        self._ui_recorder = ui_recorder
        self._state_manager = state_manager
        self._filter_chain = filter_chain
        self._reasoning_config = reasoning_config or ReasoningLoopConfigSchema()
        self._state = SymbolStateTracker()
        self._cooldowns = CooldownPolicy(
            self._state,
            self._reasoning_config,
            analyst_cooldown_cycles,
            max_consecutive_rejection_multiplier,
        )
        self._publisher = DecisionPublisher(
            redis_client,
            DecisionMessageBuilder(
                position_management,
                router.record_trader_validation_failure,
            ),
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
            raw_results: list[bool | BaseException] = await asyncio.gather(
                *(
                    self._handle_symbol_timed(symbol, cached_positions)
                    for symbol in self._symbols
                ),
                return_exceptions=True,
            )
            results: list[bool] = []
            for symbol, result in zip(self._symbols, raw_results, strict=True):
                if isinstance(result, BaseException):
                    logger.error(
                        "ReasoningLoop symbol %s raised, treating as non-interesting",
                        symbol,
                        exc_info=result,
                        extra={
                            "loop": "reasoning",
                            "symbol": symbol,
                            "cycle": cycle,
                        },
                    )
                    results.append(False)
                    continue
                results.append(result)
            interesting_count = sum(results)
            current_interval_s, stair_index = self._next_sleep_interval_s(
                interesting_count
            )
            cycle_ms = (time.monotonic() - cycle_start) * 1000
            if stair_index != self._last_idle_stair_index:
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
                        "idle_stair_index": stair_index,
                        "previous_idle_stair_index": self._last_idle_stair_index,
                    },
                )
                self._last_idle_stair_index = stair_index
            else:
                logger.debug(
                    "ReasoningLoop cycle %d complete in %.1fms, "
                    "interesting=%d/%d, sleeping %.0fs",
                    cycle,
                    cycle_ms,
                    interesting_count,
                    len(results),
                    current_interval_s,
                )
            await asyncio.sleep(current_interval_s)

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
    ) -> bool:
        if self._should_skip_symbol(symbol, cached_positions):
            return False

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

        # PipelineResult guarantees a gate whenever an Analyst decision exists.
        if result.analyst is not None and result.regime_gate is not None:
            self._cooldowns.apply_analyst_cooldown(
                symbol,
                result.analyst,
                result.regime_gate,
            )

        self._cooldowns.track_geometry_rejects(symbol, result)

        if not self._should_enqueue(result):
            self._cooldowns.track_consecutive_waits(symbol, result)
            return result.scout.verdict == "INTERESTING"

        filter_result = await self._run_filter_chain(result, cached_positions)
        if filter_result is not None and not filter_result.is_allowed:
            await self._report_filter_rejection(
                symbol,
                result.trader.action if result.trader else "UNKNOWN",
                filter_result,
            )
            return True

        size_multiplier = (
            filter_result.size_multiplier if filter_result is not None else Decimal(1)
        )
        if not await self._publisher.publish(result, size_multiplier):
            # No trade went out, so the symbol must stay eligible next cycle.
            return True

        self._cooldowns.start_post_trade_cooldown(symbol)
        return True

    def _should_enqueue(self, result: PipelineResult) -> bool:
        if result.scout.verdict != "INTERESTING":
            return False
        if result.analyst is None or not result.analyst.setup_valid:
            return False
        if result.regime_gate is None:
            return False
        if result.analyst.confluence_score < result.regime_gate:
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
