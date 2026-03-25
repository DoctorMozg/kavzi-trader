import logging
import time
from typing import Protocol

from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema

logger = logging.getLogger(__name__)

SLOW_AGENT_THRESHOLD_S = 10.0


class ScoutRunner(Protocol):
    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema: ...


class AnalystRunner(Protocol):
    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema: ...


class TraderRunner(Protocol):
    async def run(self, deps: TradingDependenciesSchema) -> TradeDecisionSchema: ...


class AgentRouter:
    """
    Routes decisions through Scout -> Analyst -> Trader.
    """

    def __init__(
        self,
        scout: ScoutRunner,
        analyst: AnalystRunner,
        trader: TraderRunner,
    ) -> None:
        self._scout = scout
        self._analyst = analyst
        self._trader = trader

    async def run(
        self,
        scout_deps: ScoutDependenciesSchema,
        analyst_deps: AnalystDependenciesSchema,
        trader_deps: TradingDependenciesSchema,
    ) -> tuple[
        ScoutDecisionSchema,
        AnalystDecisionSchema | None,
        TradeDecisionSchema | None,
    ]:
        symbol = scout_deps.symbol
        total_start = time.monotonic()
        logger.info("Agent pipeline started for %s", symbol)

        t0 = time.monotonic()
        try:
            scout_result = await self._scout.run(scout_deps)
        except Exception:
            logger.exception("Scout agent failed for %s", symbol)
            return (
                ScoutDecisionSchema(
                    verdict="SKIP", reason="agent_error",
                    pattern_detected=None,
                ),
                None,
                None,
            )
        scout_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Scout verdict=%s reason=%s pattern=%s elapsed_ms=%.1f",
            scout_result.verdict,
            scout_result.reason,
            scout_result.pattern_detected,
            scout_ms,
            extra={"symbol": symbol, "elapsed_ms": round(scout_ms, 1)},
        )
        if scout_ms / 1000 > SLOW_AGENT_THRESHOLD_S:
            logger.warning(
                "Scout agent slow for %s: %.1fs", symbol, scout_ms / 1000,
            )
        if scout_result.verdict != "INTERESTING":
            total_ms = (time.monotonic() - total_start) * 1000
            logger.info(
                "Pipeline stopped at Scout for %s in %.1fms",
                symbol, total_ms,
            )
            return scout_result, None, None

        t0 = time.monotonic()
        try:
            analyst_result = await self._analyst.run(analyst_deps)
        except Exception:
            logger.exception("Analyst agent failed for %s", symbol)
            return scout_result, None, None
        analyst_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Analyst setup_valid=%s direction=%s confluence=%d elapsed_ms=%.1f",
            analyst_result.setup_valid,
            analyst_result.direction,
            analyst_result.confluence_score,
            analyst_ms,
            extra={"symbol": symbol, "elapsed_ms": round(analyst_ms, 1)},
        )
        if analyst_ms / 1000 > SLOW_AGENT_THRESHOLD_S:
            logger.warning(
                "Analyst agent slow for %s: %.1fs", symbol, analyst_ms / 1000,
            )
        if not analyst_result.setup_valid:
            total_ms = (time.monotonic() - total_start) * 1000
            logger.info(
                "Pipeline stopped at Analyst for %s in %.1fms",
                symbol, total_ms,
            )
            return scout_result, analyst_result, None

        t0 = time.monotonic()
        try:
            trader_result = await self._trader.run(trader_deps)
        except Exception:
            logger.exception("Trader agent failed for %s", symbol)
            return scout_result, analyst_result, None
        trader_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Trader action=%s confidence=%.2f entry=%s SL=%s TP=%s elapsed_ms=%.1f",
            trader_result.action,
            trader_result.confidence,
            trader_result.suggested_entry,
            trader_result.suggested_stop_loss,
            trader_result.suggested_take_profit,
            trader_ms,
            extra={"symbol": symbol, "elapsed_ms": round(trader_ms, 1)},
        )
        if trader_ms / 1000 > SLOW_AGENT_THRESHOLD_S:
            logger.warning(
                "Trader agent slow for %s: %.1fs", symbol, trader_ms / 1000,
            )

        total_ms = (time.monotonic() - total_start) * 1000
        logger.info(
            "Agent pipeline completed for %s in %.1fms — reached tier trader",
            symbol, total_ms,
        )
        return scout_result, analyst_result, trader_result
