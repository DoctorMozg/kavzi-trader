from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.config import AgentModelConfigSchema, BrainConfigSchema
from kavzi_trader.brain.prompts.loader import PromptLoader


def _make_factory() -> AgentFactory:
    config = BrainConfigSchema(
        openrouter_api_key="test-key",
        analyst=AgentModelConfigSchema(model_id="test/analyst"),
        trader=AgentModelConfigSchema(model_id="test/trader", retries=2),
    )
    return AgentFactory(config, PromptLoader())


def test_create_analyst_agent() -> None:
    factory = _make_factory()
    agent = factory.create_analyst_agent()

    assert isinstance(agent, Agent)
    assert isinstance(agent.model, OpenAIChatModel)
    assert agent.model.model_name == "test/analyst"


def test_create_trader_agent() -> None:
    factory = _make_factory()
    agent = factory.create_trader_agent()

    assert isinstance(agent, Agent)
    assert isinstance(agent.model, OpenAIChatModel)
    assert agent.model.model_name == "test/trader"


def test_shared_openai_client() -> None:
    factory = _make_factory()
    analyst = factory.create_analyst_agent()
    trader = factory.create_trader_agent()

    assert isinstance(analyst.model, OpenAIChatModel)
    assert isinstance(trader.model, OpenAIChatModel)
    assert analyst.model.client is trader.model.client
