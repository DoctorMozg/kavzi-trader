from typing import Protocol

from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.scout_dependencies import ScoutDependenciesSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema


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


class ScoutDepsFetcher(Protocol):
    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema: ...


class AnalystDepsFetcher(Protocol):
    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema: ...


class TraderDepsFetcher(Protocol):
    async def get_trader(self, symbol: str) -> TradingDependenciesSchema: ...


class DependenciesProvider(
    ScoutDepsFetcher, AnalystDepsFetcher, TraderDepsFetcher, Protocol
):
    def indicators_available(self, symbol: str) -> bool: ...

    def clear_cycle_cache(self) -> None: ...


class ConfluenceOverrideProvider(Protocol):
    def get_confluence_override(self, direction: str) -> int | None: ...


class LLMExceptionLogger(Protocol):
    def __call__(
        self,
        symbol: str,
        agent: str,
        exc: BaseException,
        elapsed_ms: float,
    ) -> None: ...
