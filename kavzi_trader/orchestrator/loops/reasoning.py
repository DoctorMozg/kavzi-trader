from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Protocol, cast
from uuid import uuid4

from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema

logger = logging.getLogger(__name__)


class DependenciesProvider(Protocol):
    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema: ...

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema: ...

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema: ...


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
    ) -> None:
        self._symbols = symbols
        self._router = router
        self._deps_provider = deps_provider
        self._redis_client = redis_client
        self._queue_key = queue_key
        self._interval_s = interval_s
        self._report_populator = report_populator

    async def run(self) -> None:
        logger.info(
            "ReasoningLoop started with %d symbols, interval=%ds",
            len(self._symbols),
            self._interval_s,
        )
        cycle = 0
        while True:
            cycle += 1
            cycle_start = time.monotonic()
            logger.debug("ReasoningLoop cycle %d starting", cycle)
            for symbol in self._symbols:
                sym_start = time.monotonic()
                try:
                    await self._handle_symbol(symbol)
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
            cycle_ms = (time.monotonic() - cycle_start) * 1000
            logger.info(
                "ReasoningLoop cycle %d complete in %.1fms, sleeping %ds",
                cycle,
                cycle_ms,
                self._interval_s,
                extra={"cycle": cycle, "elapsed_ms": round(cycle_ms, 1)},
            )
            await asyncio.sleep(self._interval_s)

    async def _handle_symbol(self, symbol: str) -> None:
        snapshot_at_ms = int(datetime.now(UTC).timestamp() * 1000)
        scout_deps = await self._deps_provider.get_scout(symbol)
        analyst_deps = await self._deps_provider.get_analyst(symbol)
        trader_deps = await self._deps_provider.get_trader(symbol)

        scout, analyst, trader = await self._router.run(
            scout_deps=scout_deps,
            analyst_deps=analyst_deps,
            trader_deps=trader_deps,
        )
        try:
            await self._report_decisions(symbol, scout, analyst, trader)
        except Exception:
            logger.exception(
                "Failed to report decisions for %s", symbol,
            )
        if not self._should_enqueue(scout, analyst, trader):
            logger.debug(
                "No trade enqueued for %s: scout=%s analyst=%s trader=%s",
                symbol,
                scout.verdict,
                analyst.setup_valid if analyst else "N/A",
                trader.action if trader else "N/A",
            )
            return
        if trader is None:
            return
        decision = self._build_decision_message(
            trader, trader_deps, snapshot_at_ms,
        )
        try:
            await self._redis_client.client.lpush(
                self._queue_key,
                decision.model_dump_json(),
            )
        except Exception:
            logger.exception(
                "Failed to enqueue decision for %s", symbol,
                extra={"symbol": symbol},
            )
            return
        logger.info(
            "Enqueuing decision for %s: action=%s confidence=%.2f "
            "decision_id=%s",
            symbol,
            trader.action,
            trader.confidence,
            decision.decision_id,
            extra={
                "symbol": symbol,
                "decision_id": decision.decision_id,
                "action": trader.action,
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
            summary="Verdict: %s — %s" % (scout.verdict, scout.reason),
            details=scout.pattern_detected,
        )
        if analyst is not None:
            await self._report_populator.record_action(
                action_type="analyst_review",
                symbol=symbol,
                summary="Valid: %s, Direction: %s, Confluence: %d/10"
                % (analyst.setup_valid, analyst.direction, analyst.confluence_score),
                details=analyst.reasoning,
            )
        if trader is not None:
            await self._report_populator.record_action(
                action_type="trader_decision",
                symbol=symbol,
                summary="Action: %s, Confidence: %.0f%%"
                % (trader.action, trader.confidence * 100),
                details=trader.reasoning,
            )

    def _should_enqueue(
        self,
        scout: ScoutDecisionSchema,
        analyst: AnalystDecisionSchema | None,
        trader: TradeDecisionSchema | None,
    ) -> bool:
        if scout.verdict != "INTERESTING":
            return False
        if analyst is None or not analyst.setup_valid:
            return False
        if trader is None:
            return False
        return trader.action in {"BUY", "SELL", "CLOSE"}

    def _build_decision_message(
        self,
        trader: TradeDecisionSchema,
        deps: TradingDependenciesSchema,
        snapshot_at_ms: int,
    ) -> DecisionMessageSchema:
        decision_id = str(uuid4())
        position_management = PositionManagementConfigSchema()
        if trader.position_management is not None:
            position_management = PositionManagementConfigSchema.model_validate(
                trader.position_management.model_dump(),
            )

        entry_price = trader.suggested_entry or deps.current_price
        stop_loss = trader.suggested_stop_loss or entry_price
        take_profit = trader.suggested_take_profit or entry_price
        atr = deps.indicators.atr_14 or Decimal("0")
        if trader.action not in {"BUY", "SELL", "CLOSE"}:
            raise ValueError("Unsupported action for execution queue")
        action = cast(Literal["BUY", "SELL", "CLOSE"], trader.action)

        return DecisionMessageSchema(
            decision_id=decision_id,
            symbol=deps.symbol,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=Decimal("0"),
            reasoning=trader.reasoning,
            raw_confidence=trader.confidence,
            calibrated_confidence=trader.calibrated_confidence
            if trader.calibrated_confidence is not None
            else trader.confidence,
            volatility_regime=deps.volatility_regime,
            position_management=position_management,
            created_at_ms=snapshot_at_ms,
            expires_at_ms=snapshot_at_ms + 60_000,
            current_atr=atr,
            atr_history=deps.atr_history,
        )
