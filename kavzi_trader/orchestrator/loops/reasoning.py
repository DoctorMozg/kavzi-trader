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
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema

logger = logging.getLogger(__name__)

_BACKOFF_MULTIPLIER = 2.0
_MAX_BACKOFF_FACTOR = 6.0


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
        self._cooldowns: dict[str, int] = {}

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
            results: list[bool] = await asyncio.gather(
                *(self._handle_symbol_timed(symbol) for symbol in self._symbols),
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

    async def _handle_symbol_timed(self, symbol: str) -> bool:
        sym_start = time.monotonic()
        interesting = False
        try:
            interesting = await self._handle_symbol(symbol)
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

    async def _get_open_position_symbols(self) -> set[str]:
        if self._state_manager is None:
            return set()
        try:
            positions = await self._state_manager.get_all_positions()
            return {p.symbol for p in positions}
        except Exception:
            logger.exception("Failed to fetch open positions for skip check")
            return set()

    async def _handle_symbol(self, symbol: str) -> bool:
        remaining = self._cooldowns.get(symbol, 0)
        if remaining > 0:
            self._cooldowns[symbol] = remaining - 1
            logger.debug(
                "Skipping %s: cooldown remaining %d cycles",
                symbol,
                remaining - 1,
            )
            return False

        open_symbols = await self._get_open_position_symbols()
        if symbol in open_symbols:
            logger.debug("Skipping %s: open position exists", symbol)
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

        if result.analyst is not None:
            self._cooldowns[symbol] = self._analyst_cooldown_cycles

        if not self._should_enqueue(result):
            return result.scout.verdict == "INTERESTING"
        self._cooldowns[symbol] = self._analyst_cooldown_cycles * 3
        await self._enqueue_decision(result)
        return True

    def _should_enqueue(self, result: PipelineResult) -> bool:
        if result.scout.verdict != "INTERESTING":
            return False
        if result.analyst is None or not result.analyst.setup_valid:
            return False
        if result.trader is None:
            return False
        return result.trader.action in {"LONG", "SHORT", "CLOSE"}

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
                    f"Confluence: {analyst.confluence_score}/10"
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
        )
