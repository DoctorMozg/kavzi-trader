import logging
from typing import Protocol

import httpx2
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from kavzi_trader.brain.config import AgentModelConfigSchema, BrainConfigSchema
from kavzi_trader.brain.confluence_thresholds import (
    COUNTER_TREND_GATE_BUMP,
    all_regime_gates,
)
from kavzi_trader.brain.context.context_dicts import (
    RegimeGateDict,
    SystemPromptContextDict,
)
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.commons.trading_constants import MAX_TP_ATR
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.symbol_tier import SymbolTier, SymbolTierConfigSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema
from kavzi_trader.external.config import SynthesizerConfigSchema
from kavzi_trader.external.synthesizer import SynthesizerOutputSchema

logger = logging.getLogger(__name__)

_SYNTHESIZER_TIMEOUT_S = 30.0


class TierConfigSource(Protocol):
    """Tier config lookup the factory needs; the spine registry satisfies it."""

    def get_config_for_tier(self, tier: SymbolTier) -> SymbolTierConfigSchema: ...


class AgentFactory:
    """Creates PydanticAI Agent instances configured for OpenRouter."""

    def __init__(
        self,
        config: BrainConfigSchema,
        prompt_loader: PromptLoader,
        risk_config: RiskConfigSchema,
        tier_registry: TierConfigSource,
    ) -> None:
        self._config = config
        self._prompt_loader = prompt_loader
        self._system_prompt_context = SystemPromptContextDict(
            min_rr_ratio=str(risk_config.min_rr_ratio),
            drawdown_pause_percent=str(risk_config.drawdown_pause_percent),
            drawdown_close_all_percent=str(risk_config.drawdown_close_all_percent),
            regime_gates=[
                RegimeGateDict(regime=regime.value, gate=gate)
                for regime, gate in all_regime_gates().items()
            ],
            counter_trend_gate_bump=COUNTER_TREND_GATE_BUMP,
            max_tp_atr=str(MAX_TP_ATR),
            max_stop_atr=str(MAX_TP_ATR / risk_config.min_rr_ratio),
            volatility_low_threshold=str(risk_config.volatility_low_threshold),
            volatility_high_threshold=str(risk_config.volatility_high_threshold),
            volatility_extreme_threshold=str(risk_config.volatility_extreme_threshold),
            tier_1_min_confidence=str(
                tier_registry.get_config_for_tier(SymbolTier.TIER_1).min_confidence
            ),
            tier_2_min_confidence=str(
                tier_registry.get_config_for_tier(SymbolTier.TIER_2).min_confidence
            ),
            tier_3_min_confidence=str(
                tier_registry.get_config_for_tier(SymbolTier.TIER_3).min_confidence
            ),
        )
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
                api_key=config.openrouter_api_key.get_secret_value(),
                timeout=httpx2.Timeout(timeout_s, connect=10.0),
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
        system_prompt = self._prompt_loader.render_system_prompt(
            "analyst", context=self._system_prompt_context
        )
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
        system_prompt = self._prompt_loader.render_system_prompt(
            "trader", context=self._system_prompt_context
        )
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

    def create_synthesizer_agent(
        self,
        config: SynthesizerConfigSchema,
    ) -> Agent[None, SynthesizerOutputSchema]:
        model = OpenAIChatModel(config.model_id, provider=self._provider)
        settings = ModelSettings(
            temperature=config.temperature,
            timeout=_SYNTHESIZER_TIMEOUT_S,
        )
        if config.seed is not None:
            settings["seed"] = config.seed
        logger.info("Creating synthesizer agent with model %s", config.model_id)
        return Agent(
            model,
            output_type=SynthesizerOutputSchema,
            instructions=self._prompt_loader.render_system_prompt("synthesizer"),
            model_settings=settings,
            retries=config.retries,
        )

    @staticmethod
    def _build_tier_settings(
        tier: AgentModelConfigSchema,
        global_timeout_s: float,
    ) -> ModelSettings:
        effective_timeout = (
            tier.timeout_s if tier.timeout_s is not None else global_timeout_s
        )
        settings = ModelSettings(
            temperature=tier.temperature,
            timeout=effective_timeout,
            extra_body={"provider": {"sort": "latency"}},
        )
        if tier.seed is not None:
            settings["seed"] = tier.seed
        return settings
