from typing import Protocol

from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema


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
        scout_result = await self._scout.run(scout_deps)
        if scout_result.verdict != "INTERESTING":
            return scout_result, None, None
        analyst_result = await self._analyst.run(analyst_deps)
        if not analyst_result.setup_valid:
            return scout_result, analyst_result, None
        trader_result = await self._trader.run(trader_deps)
        return scout_result, analyst_result, trader_result
