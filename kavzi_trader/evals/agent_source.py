from typing import Protocol

from pydantic_ai import Agent

from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema


class AgentSource(Protocol):
    """Where the runner gets its LLM agents; the live AgentFactory satisfies it."""

    def create_analyst_agent(
        self,
    ) -> Agent[AnalystDependenciesSchema, AnalystDecisionSchema]: ...

    def create_trader_agent(
        self,
    ) -> Agent[TradingDependenciesSchema, TradeDecisionSchema]: ...
