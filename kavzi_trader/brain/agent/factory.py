import logging

import httpx
from openai import AsyncOpenAI
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from kavzi_trader.brain.config import BrainConfigSchema
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema

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

    def create_scout_agent(
        self,
    ) -> Agent[ScoutDependenciesSchema, ScoutDecisionSchema]:
        model = OpenAIChatModel(
            self._config.scout.model_id,
            provider=self._provider,
        )
        system_prompt = self._prompt_loader.render_system_prompt("scout")
        logger.info(
            "Creating scout agent with model %s",
            self._config.scout.model_id,
        )
        return Agent(
            model,
            output_type=PromptedOutput(ScoutDecisionSchema),
            deps_type=ScoutDependenciesSchema,
            instructions=system_prompt,
            retries=self._config.scout.retries,
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
            retries=self._config.trader.retries,
        )
