import logging
from typing import Protocol

import httpx2
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from kavzi_trader.brain.config import (
    ANTHROPIC_AGENT_DEFAULTS,
    AgentModelConfigSchema,
    BrainConfigSchema,
)
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
from kavzi_trader.commons.llm_provider import AnthropicEffort, LlmProvider
from kavzi_trader.commons.trading_constants import MAX_TP_ATR
from kavzi_trader.domain.analyst_decision import (
    ANALYST_REASONING_MAX_CHARS,
    KEY_LEVEL_REASON_MAX_CHARS,
    MAX_KEY_LEVELS,
    AnalystDecisionSchema,
)
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.symbol_tier import SymbolTier, SymbolTierConfigSchema
from kavzi_trader.domain.trade_decision import (
    TRADER_REASONING_MAX_CHARS,
    TradeDecisionSchema,
)
from kavzi_trader.external.config import SynthesizerConfigSchema
from kavzi_trader.external.synthesizer import SynthesizerOutputSchema

logger = logging.getLogger(__name__)

_SYNTHESIZER_TIMEOUT_S = 30.0
_CLIENT_CONNECT_TIMEOUT_S = 10.0
# Beta that enables `fallbacks`: on a refusal the API retries the request on
# a substitute model server-side instead of returning stop_reason "refusal".
_SERVER_SIDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class TierConfigSource(Protocol):
    """Tier config lookup the factory needs; the spine registry satisfies it."""

    def get_config_for_tier(self, tier: SymbolTier) -> SymbolTierConfigSchema: ...


class LlmAgentSettingsSource(Protocol):
    """Per-agent LLM settings shared by the tier and synthesizer configs."""

    @property
    def provider(self) -> LlmProvider: ...

    @property
    def model_id(self) -> str | None: ...

    @property
    def effort(self) -> AnthropicEffort | None: ...

    @property
    def temperature(self) -> float: ...

    @property
    def seed(self) -> int | None: ...


class AgentFactory:
    """Creates PydanticAI agents for OpenRouter or the direct Anthropic API."""

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
            analyst_reasoning_max_chars=ANALYST_REASONING_MAX_CHARS,
            trader_reasoning_max_chars=TRADER_REASONING_MAX_CHARS,
            key_level_reason_max_chars=KEY_LEVEL_REASON_MAX_CHARS,
            max_key_levels=MAX_KEY_LEVELS,
        )
        self._openrouter_provider: OpenAIProvider | None = None
        self._anthropic_provider: AnthropicProvider | None = None
        timeout_s = config.request_timeout_s
        self._analyst_settings = self._build_tier_settings(
            "analyst", config.analyst, timeout_s
        )
        self._trader_settings = self._build_tier_settings(
            "trader", config.trader, timeout_s
        )

    def _get_openrouter_provider(self) -> OpenAIProvider:
        if self._openrouter_provider is None:
            timeout_s = self._config.request_timeout_s
            logger.info("OpenRouter HTTP timeout set to %.0fs", timeout_s)
            self._openrouter_provider = OpenAIProvider(
                openai_client=AsyncOpenAI(
                    base_url=self._config.openrouter_base_url,
                    api_key=self._config.openrouter_api_key.get_secret_value(),
                    timeout=httpx2.Timeout(
                        timeout_s, connect=_CLIENT_CONNECT_TIMEOUT_S
                    ),
                    default_headers={
                        "HTTP-Referer": "https://github.com/kavzitrader",
                        "X-Title": "KavziTrader",
                    },
                ),
            )
        return self._openrouter_provider

    def _get_anthropic_provider(self) -> AnthropicProvider:
        if self._anthropic_provider is None:
            logger.info(
                "Anthropic client created: max_retries=%d",
                self._config.anthropic_max_retries,
            )
            self._anthropic_provider = AnthropicProvider(
                anthropic_client=AsyncAnthropic(
                    api_key=self._config.anthropic_api_key.get_secret_value(),
                    max_retries=self._config.anthropic_max_retries,
                ),
            )
        return self._anthropic_provider

    def _build_model(
        self, role: str, source: LlmAgentSettingsSource
    ) -> tuple[Model, str]:
        if source.provider is LlmProvider.ANTHROPIC:
            model_id = source.model_id or ANTHROPIC_AGENT_DEFAULTS[role].model_id
            model: Model = AnthropicModel(
                model_id, provider=self._get_anthropic_provider()
            )
            return model, model_id
        if source.model_id is None:
            msg = f"{role}: model_id is required for provider openrouter"
            raise ValueError(msg)
        model = OpenAIChatModel(
            source.model_id, provider=self._get_openrouter_provider()
        )
        return model, source.model_id

    def create_analyst_agent(
        self,
    ) -> Agent[AnalystDependenciesSchema, AnalystDecisionSchema]:
        model, model_id = self._build_model("analyst", self._config.analyst)
        system_prompt = self._prompt_loader.render_system_prompt(
            "analyst", context=self._system_prompt_context
        )
        logger.info(
            "Creating analyst agent with %s model %s",
            self._config.analyst.provider,
            model_id,
        )
        return Agent(
            model,
            output_type=self._output_spec(
                self._config.analyst.provider, AnalystDecisionSchema
            ),
            deps_type=AnalystDependenciesSchema,
            instructions=system_prompt,
            model_settings=self._analyst_settings,
            retries=self._config.analyst.retries,
        )

    def create_trader_agent(
        self,
    ) -> Agent[TradingDependenciesSchema, TradeDecisionSchema]:
        model, model_id = self._build_model("trader", self._config.trader)
        system_prompt = self._prompt_loader.render_system_prompt(
            "trader", context=self._system_prompt_context
        )
        logger.info(
            "Creating trader agent with %s model %s",
            self._config.trader.provider,
            model_id,
        )
        return Agent(
            model,
            output_type=self._output_spec(
                self._config.trader.provider, TradeDecisionSchema
            ),
            deps_type=TradingDependenciesSchema,
            instructions=system_prompt,
            model_settings=self._trader_settings,
            retries=self._config.trader.retries,
        )

    def create_synthesizer_agent(
        self,
        config: SynthesizerConfigSchema,
    ) -> Agent[None, SynthesizerOutputSchema]:
        model, model_id = self._build_model("synthesizer", config)
        settings = self._build_synthesizer_settings(config)
        logger.info(
            "Creating synthesizer agent with %s model %s", config.provider, model_id
        )
        return Agent(
            model,
            output_type=self._output_spec(config.provider, SynthesizerOutputSchema),
            instructions=self._prompt_loader.render_system_prompt("synthesizer"),
            model_settings=settings,
            retries=config.retries,
        )

    @staticmethod
    def _output_spec[TOutput](
        provider: LlmProvider, output_cls: type[TOutput]
    ) -> type[TOutput] | NativeOutput[TOutput]:
        # Claude 5.5 rejects the forced tool_choice that tool output relies on,
        # so Anthropic agents use structured outputs (output_config.format).
        if provider is LlmProvider.ANTHROPIC:
            return NativeOutput(output_cls)
        return output_cls

    @staticmethod
    def _build_anthropic_settings(
        role: str,
        source: LlmAgentSettingsSource,
        timeout_s: float,
    ) -> ModelSettings:
        if source.seed is not None or source.temperature != 0.0:
            logger.warning(
                "%s: temperature/seed are not sent to Anthropic and are ignored",
                role,
            )
        effort = source.effort or ANTHROPIC_AGENT_DEFAULTS[role].effort
        return AnthropicModelSettings(
            timeout=timeout_s,
            anthropic_effort=effort,
            # Cache only the rendered system prompt; per-candle context lives in
            # the user prompt and stays outside the cached prefix.
            anthropic_cache_instructions=True,
            anthropic_betas=[_SERVER_SIDE_FALLBACK_BETA],
            extra_body={"fallbacks": "default"},
        )

    @classmethod
    def _build_tier_settings(
        cls,
        role: str,
        tier: AgentModelConfigSchema,
        global_timeout_s: float,
    ) -> ModelSettings:
        effective_timeout = (
            tier.timeout_s if tier.timeout_s is not None else global_timeout_s
        )
        if tier.provider is LlmProvider.ANTHROPIC:
            return cls._build_anthropic_settings(role, tier, effective_timeout)
        settings = ModelSettings(
            temperature=tier.temperature,
            timeout=effective_timeout,
            extra_body={"provider": {"sort": "latency"}},
        )
        if tier.seed is not None:
            settings["seed"] = tier.seed
        return settings

    @classmethod
    def _build_synthesizer_settings(
        cls, config: SynthesizerConfigSchema
    ) -> ModelSettings:
        if config.provider is LlmProvider.ANTHROPIC:
            return cls._build_anthropic_settings(
                "synthesizer", config, _SYNTHESIZER_TIMEOUT_S
            )
        settings = ModelSettings(
            temperature=config.temperature,
            timeout=_SYNTHESIZER_TIMEOUT_S,
        )
        if config.seed is not None:
            settings["seed"] = config.seed
        return settings
