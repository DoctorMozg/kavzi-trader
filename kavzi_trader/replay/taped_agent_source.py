import logging

from pydantic_ai import Agent
from pydantic_ai.models import infer_model

from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema
from kavzi_trader.evals.agent_source import AgentSource
from kavzi_trader.replay.llm_tape import LlmTape
from kavzi_trader.replay.replay_model import ReplayModel

logger = logging.getLogger(__name__)


class TapedAgentSource:
    """Wraps each agent's model so its calls go through one shared tape."""

    def __init__(self, agents: AgentSource, tape: LlmTape, *, record: bool) -> None:
        self._agents = agents
        self._tape = tape
        self._record = record
        self._models: list[ReplayModel] = []

    @property
    def provider_calls(self) -> int:
        return sum(m.provider_calls for m in self._models)

    @property
    def tape_misses(self) -> int:
        return sum(m.tape_misses for m in self._models)

    @property
    def model_names(self) -> list[str]:
        return [m.model_name for m in self._models]

    def create_analyst_agent(
        self,
    ) -> Agent[AnalystDependenciesSchema, AnalystDecisionSchema]:
        agent = self._agents.create_analyst_agent()
        agent.model = self._wrap(agent)
        return agent

    def create_trader_agent(
        self,
    ) -> Agent[TradingDependenciesSchema, TradeDecisionSchema]:
        agent = self._agents.create_trader_agent()
        agent.model = self._wrap(agent)
        return agent

    def _wrap(
        self,
        agent: Agent[AnalystDependenciesSchema, AnalystDecisionSchema]
        | Agent[TradingDependenciesSchema, TradeDecisionSchema],
    ) -> ReplayModel:
        if agent.model is None:
            msg = f"agent {agent.name!r} has no model to tape"
            raise ValueError(msg)
        model = ReplayModel(infer_model(agent.model), self._tape, record=self._record)
        logger.info(
            "Taping %s (record=%s, %d responses on tape)",
            model.model_name,
            self._record,
            len(self._tape),
        )
        self._models.append(model)
        return model
