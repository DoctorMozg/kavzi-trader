import asyncio
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

import pytest
from pydantic import SecretStr
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel

from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.config import BrainConfigSchema
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.symbol_tier import SymbolTier, SymbolTierConfigSchema
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry


class RequestCapturedError(Exception):
    """Raised by the stub transport once the outgoing request was recorded."""


@pytest.fixture
def tier_registry() -> SymbolTierRegistry:
    tier_config = SymbolTierConfigSchema(
        risk_per_trade_percent=Decimal("3.0"),
        max_leverage=5,
        max_exposure_percent=Decimal("20.0"),
        min_confidence=Decimal("0.70"),
        crowded_long_zscore=Decimal("2.0"),
        crowded_short_zscore=Decimal("-2.0"),
    )
    return SymbolTierRegistry(
        tier_configs=dict.fromkeys(SymbolTier, tier_config),
        symbol_map={},
    )


@pytest.fixture
def make_factory(
    tier_registry: SymbolTierRegistry,
) -> Callable[[Mapping[str, object]], AgentFactory]:
    def _make(brain: Mapping[str, object]) -> AgentFactory:
        config = BrainConfigSchema.model_validate(
            {
                "openrouter_api_key": SecretStr("or-test-key"),
                "anthropic_api_key": SecretStr("an-test-key"),
                **brain,
            }
        )
        return AgentFactory(
            config,
            PromptLoader(),
            risk_config=RiskConfigSchema(),
            tier_registry=tier_registry,
        )

    return _make


@pytest.fixture
def sent_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Agent[Any, Any]], list[dict[str, Any]]]:
    """Run an Anthropic agent against a stub and return the create() kwargs."""

    def _capture(agent: Agent[Any, Any]) -> list[dict[str, Any]]:
        sent: list[dict[str, Any]] = []

        async def fake_create(**kwargs: Any) -> object:
            sent.append(kwargs)
            raise RequestCapturedError

        assert isinstance(agent.model, AnthropicModel)
        monkeypatch.setattr(agent.model.client.beta.messages, "create", fake_create)
        with pytest.raises(RequestCapturedError):
            asyncio.run(agent.run("prompt"))
        return sent

    return _capture
