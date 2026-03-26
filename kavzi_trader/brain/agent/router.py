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
    ) -> TradeDecisionSchema: ...


class DependenciesProvider(Protocol):
    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema: ...

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema: ...

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema: ...

    def clear_cycle_cache(self) -> None: ...


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


class AgentRouter:
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
        symbol: str,
        deps_provider: DependenciesProvider,
    ) -> PipelineResult:
        total_start = time.monotonic()
        logger.info("Agent pipeline started for %s", symbol)

        scout_result = await self._run_scout(symbol, deps_provider)
        if scout_result is None:
            return PipelineResult(scout=_SKIP_ERROR)
        if scout_result.verdict != "INTERESTING":
            self._log_stop("Scout", symbol, total_start)
            return PipelineResult(scout=scout_result)

        analyst_result = await self._run_analyst(symbol, deps_provider)
        if analyst_result is None:
            return PipelineResult(scout=scout_result)
        if not analyst_result.setup_valid:
            self._log_stop("Analyst", symbol, total_start)
            return PipelineResult(scout=scout_result, analyst=analyst_result)

        trader_result, trader_deps = await self._run_trader(
            symbol,
            deps_provider,
            analyst_result,
        )
        if trader_result is None:
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
            trader=trader_result,
            trader_deps=trader_deps,
        )

    async def _run_scout(
        self,
        symbol: str,
        deps_provider: DependenciesProvider,
    ) -> ScoutDecisionSchema | None:
        deps = await deps_provider.get_scout(symbol)
        t0 = time.monotonic()
        try:
            result = await self._scout.run(deps)
        except Exception:
            logger.exception("Scout agent failed for %s", symbol)
            return None
        ms = (time.monotonic() - t0) * 1000
        self._warn_slow("Scout", symbol, ms)
        return result

    async def _run_analyst(
        self,
        symbol: str,
        deps_provider: DependenciesProvider,
    ) -> AnalystDecisionSchema | None:
        deps = await deps_provider.get_analyst(symbol)
        t0 = time.monotonic()
        try:
            result = await self._analyst.run(deps)
        except Exception:
            logger.exception("Analyst agent failed for %s", symbol)
            return None
        ms = (time.monotonic() - t0) * 1000
        self._warn_slow("Analyst", symbol, ms)
        return result

    async def _run_trader(
        self,
        symbol: str,
        deps_provider: DependenciesProvider,
        analyst_result: AnalystDecisionSchema,
    ) -> tuple[TradeDecisionSchema | None, TradingDependenciesSchema | None]:
        deps = await deps_provider.get_trader(symbol)
        t0 = time.monotonic()
        try:
            result = await self._trader.run(deps, analyst_result=analyst_result)
        except Exception:
            logger.exception("Trader agent failed for %s", symbol)
            return None, None
        ms = (time.monotonic() - t0) * 1000
        self._warn_slow("Trader", symbol, ms)
        return result, deps

    @staticmethod
    def _warn_slow(agent: str, symbol: str, ms: float) -> None:
        if ms / 1000 > SLOW_AGENT_THRESHOLD_S:
            logger.warning(
                "%s agent slow for %s: %.1fs",
                agent,
                symbol,
                ms / 1000,
            )

    @staticmethod
    def _log_stop(agent: str, symbol: str, start: float) -> None:
        total_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Pipeline stopped at %s for %s in %.1fms",
            agent,
            symbol,
            total_ms,
        )
