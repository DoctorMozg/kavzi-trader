import logging
import time
from typing import Protocol

from pydantic import BaseModel, ConfigDict

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
        scout_pattern: str | None = None,
    ) -> TradeDecisionSchema: ...


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

        scout_deps = await self._fetch_scout_deps(symbol, deps_provider)

        scout_result = await self._invoke_scout(symbol, scout_deps)
        if scout_result is None:
            scout_result = _SKIP_ERROR
        if scout_result.verdict != "INTERESTING":
            self._log_stop("Scout", symbol, total_start)
            return PipelineResult(scout=scout_result)

        analyst_result = await self._run_analyst(symbol, deps_provider)
        if analyst_result is None:
            return PipelineResult(scout=scout_result)
        if not analyst_result.setup_valid:
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
        self._log_analyst_inputs(deps)
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
        scout_pattern: str | None = None,
    ) -> _TraderRunResult:
        deps = await deps_provider.get_trader(symbol)
        self._log_trader_inputs(deps, analyst_result, scout_pattern)
        t0 = time.monotonic()
        try:
            result = await self._trader.run(
                deps,
                analyst_result=analyst_result,
                scout_pattern=scout_pattern,
            )
        except Exception:
            logger.exception("Trader agent failed for %s", symbol)
            return _TraderRunResult()
        ms = (time.monotonic() - t0) * 1000
        self._warn_slow("Trader", symbol, ms)
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
