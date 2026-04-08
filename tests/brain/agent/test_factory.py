from decimal import Decimal

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.config import AgentModelConfigSchema, BrainConfigSchema
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.symbol_tier import SymbolTier, SymbolTierConfigSchema
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry


def _make_tier_registry() -> SymbolTierRegistry:
    """Build a minimal tier registry for factory tests."""
    tier_config = SymbolTierConfigSchema(
        risk_per_trade_percent=Decimal("3.0"),
        max_leverage=5,
        max_exposure_percent=Decimal("20.0"),
        min_confidence=Decimal("0.70"),
        crowded_long_zscore=Decimal("2.0"),
        crowded_short_zscore=Decimal("-2.0"),
    )
    tier_configs = {
        SymbolTier.TIER_1: tier_config,
        SymbolTier.TIER_2: tier_config,
        SymbolTier.TIER_3: tier_config,
    }
    return SymbolTierRegistry(tier_configs=tier_configs, symbol_map={})


def _make_factory() -> AgentFactory:
    config = BrainConfigSchema(
        openrouter_api_key="test-key",
        analyst=AgentModelConfigSchema(model_id="test/analyst"),
        trader=AgentModelConfigSchema(model_id="test/trader", retries=2),
    )
    return AgentFactory(
        config,
        PromptLoader(),
        risk_config=RiskConfigSchema(),
        tier_registry=_make_tier_registry(),
    )


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
