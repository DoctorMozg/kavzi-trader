import logging

import httpx
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from kavzi_trader.brain.config import AgentModelConfigSchema, BrainConfigSchema
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)

logger = logging.getLogger(__name__)


class AgentFactory:
    """Creates PydanticAI Agent instances configured for OpenRouter."""

    def __init__(
        self,
        config: BrainConfigSchema,
        prompt_loader: PromptLoader,
    ) -> None:
        self._config = config
        self._prompt_loader = prompt_loader
        timeout_s = config.request_timeout_s
        logger.info(
            "OpenRouter HTTP timeout set to %.0fs",
            timeout_s,
        )
        self._analyst_settings = self._build_tier_settings(
            config.analyst,
            timeout_s,
        )
        self._trader_settings = self._build_tier_settings(
            config.trader,
            timeout_s,
        )
        self._provider = OpenAIProvider(
            openai_client=AsyncOpenAI(
                base_url=config.openrouter_base_url,
                api_key=config.openrouter_api_key,
                timeout=httpx.Timeout(timeout_s, connect=10.0),
                default_headers={
                    "HTTP-Referer": "https://github.com/kavzitrader",
                    "X-Title": "KavziTrader",
                },
            ),
        )

    def create_analyst_agent(
        self,
    ) -> Agent[AnalystDependenciesSchema, AnalystDecisionSchema]:
        model = OpenAIChatModel(
            self._config.analyst.model_id,
            provider=self._provider,
        )
        system_prompt = self._prompt_loader.render_system_prompt("analyst")
        logger.info(
            "Creating analyst agent with model %s",
            self._config.analyst.model_id,
        )
        return Agent(
            model,
            output_type=AnalystDecisionSchema,
            deps_type=AnalystDependenciesSchema,
            instructions=system_prompt,
            model_settings=self._analyst_settings,
            retries=self._config.analyst.retries,
        )

    def create_trader_agent(
        self,
    ) -> Agent[TradingDependenciesSchema, TradeDecisionSchema]:
        model = OpenAIChatModel(
            self._config.trader.model_id,
            provider=self._provider,
        )
        system_prompt = self._prompt_loader.render_system_prompt("trader")
        logger.info(
            "Creating trader agent with model %s",
            self._config.trader.model_id,
        )
        return Agent(
            model,
            output_type=TradeDecisionSchema,
            deps_type=TradingDependenciesSchema,
            instructions=system_prompt,
            model_settings=self._trader_settings,
            retries=self._config.trader.retries,
        )

    @staticmethod
    def _build_tier_settings(
        tier: AgentModelConfigSchema,
        global_timeout_s: float,
    ) -> ModelSettings:
        effective_timeout = tier.timeout_s or global_timeout_s
        settings = ModelSettings(
            temperature=tier.temperature,
            timeout=effective_timeout,
            extra_body={"provider": {"sort": "latency"}},
        )
        if tier.seed is not None:
            settings["seed"] = tier.seed
        return settings
