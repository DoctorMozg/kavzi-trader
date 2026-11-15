import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

import pytest
from anthropic import Omit
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaUsage
from pydantic import SecretStr
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import ContentFilterError
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel

from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.agent.llm_error_logging import log_llm_exception
from kavzi_trader.brain.config import (
    ANTHROPIC_AGENT_DEFAULTS,
    ANTHROPIC_MAX_OUTPUT_TOKENS,
    AgentModelConfigSchema,
    BrainConfigSchema,
)
from kavzi_trader.commons.llm_provider import LlmProvider
from kavzi_trader.config import AppConfig
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.external.config import SynthesizerConfigSchema

MakeFactory = Callable[[Mapping[str, object]], AgentFactory]
SentRequests = Callable[[Agent[Any, Any]], list[dict[str, Any]]]

ALL_ANTHROPIC: dict[str, object] = {
    "analyst": {"provider": "anthropic"},
    "trader": {"provider": "anthropic"},
}
ROLES = ["analyst", "trader", "synthesizer"]


def _model(agent: Agent[Any, Any]) -> AnthropicModel:
    assert isinstance(agent.model, AnthropicModel)
    return agent.model


def _create_agent(factory: AgentFactory, role: str) -> Agent[Any, Any]:
    if role == "analyst":
        return factory.create_analyst_agent()
    if role == "trader":
        return factory.create_trader_agent()
    return factory.create_synthesizer_agent(
        SynthesizerConfigSchema(provider=LlmProvider.ANTHROPIC)
    )


class TestProviderSelection:
    def test_defaults_stay_on_openrouter(self, make_factory: MakeFactory) -> None:
        factory = make_factory({})
        for agent in (factory.create_analyst_agent(), factory.create_trader_agent()):
            assert isinstance(agent.model, OpenAIChatModel)

    def test_anthropic_agents_use_anthropic_model(
        self, make_factory: MakeFactory
    ) -> None:
        factory = make_factory(ALL_ANTHROPIC)
        analyst = factory.create_analyst_agent()
        trader = factory.create_trader_agent()
        synth = _create_agent(factory, "synthesizer")

        assert isinstance(analyst.model, AnthropicModel)
        assert isinstance(trader.model, AnthropicModel)
        assert isinstance(synth.model, AnthropicModel)
        assert _model(analyst).client is _model(trader).client

    def test_mixed_providers(self, make_factory: MakeFactory) -> None:
        factory = make_factory({"trader": {"provider": "anthropic"}})
        assert isinstance(factory.create_analyst_agent().model, OpenAIChatModel)
        assert isinstance(factory.create_trader_agent().model, AnthropicModel)

    def test_default_models_per_agent(self, make_factory: MakeFactory) -> None:
        factory = make_factory(ALL_ANTHROPIC)
        assert _model(factory.create_analyst_agent()).model_name == "claude-sonnet-5-5"
        assert _model(factory.create_trader_agent()).model_name == "claude-opus-5-5"
        synth = _create_agent(factory, "synthesizer")
        assert _model(synth).model_name == "claude-sonnet-5-5"

    def test_configured_model_wins_over_default(
        self, make_factory: MakeFactory
    ) -> None:
        factory = make_factory(
            {"analyst": {"provider": "anthropic", "model_id": "claude-custom"}}
        )
        assert _model(factory.create_analyst_agent()).model_name == "claude-custom"

    def test_openrouter_requires_model_id(self) -> None:
        with pytest.raises(ValueError, match="model_id is required"):
            AgentModelConfigSchema(provider=LlmProvider.OPENROUTER)

    def test_synthesizer_model_default_depends_on_provider(self) -> None:
        config = SynthesizerConfigSchema()
        assert config.provider is LlmProvider.OPENROUTER
        assert config.model_id == "deepseek/deepseek-chat-v3-0324"
        anthropic = SynthesizerConfigSchema(provider=LlmProvider.ANTHROPIC)
        assert anthropic.model_id is None


class TestAnthropicRequest:
    @pytest.mark.parametrize("role", ROLES)
    def test_no_sampling_and_no_forced_tool_choice(
        self, make_factory: MakeFactory, sent_requests: SentRequests, role: str
    ) -> None:
        agent = _create_agent(make_factory(ALL_ANTHROPIC), role)
        (request,) = sent_requests(agent)

        tool_choice = request["tool_choice"]
        assert isinstance(tool_choice, Omit) or tool_choice == {"type": "auto"}
        assert not request.get("tools")
        for banned in ("temperature", "top_p", "top_k", "seed"):
            assert banned not in request
            assert banned not in request["extra_body"]

    @pytest.mark.parametrize("role", ROLES)
    def test_structured_output_and_default_effort(
        self, make_factory: MakeFactory, sent_requests: SentRequests, role: str
    ) -> None:
        agent = _create_agent(make_factory(ALL_ANTHROPIC), role)
        (request,) = sent_requests(agent)

        output_config = request["output_config"]
        assert output_config["format"]["type"] == "json_schema"
        assert output_config["effort"] == ANTHROPIC_AGENT_DEFAULTS[role].effort

    @pytest.mark.parametrize("role", ROLES)
    def test_output_is_capped_and_not_streamed(
        self, make_factory: MakeFactory, sent_requests: SentRequests, role: str
    ) -> None:
        # Uncapped, pydantic-ai streams up to the model max and the read timeout
        # never fires; one eval Analyst call ran 537 s and 128k tokens that way.
        agent = _create_agent(make_factory(ALL_ANTHROPIC), role)
        (request,) = sent_requests(agent)

        assert request["max_tokens"] == ANTHROPIC_MAX_OUTPUT_TOKENS
        assert request.get("stream") is not True

    def test_default_efforts(self) -> None:
        assert ANTHROPIC_AGENT_DEFAULTS["analyst"].effort == "medium"
        assert ANTHROPIC_AGENT_DEFAULTS["trader"].effort == "medium"
        assert ANTHROPIC_AGENT_DEFAULTS["synthesizer"].effort == "low"

    def test_configured_effort_wins(
        self, make_factory: MakeFactory, sent_requests: SentRequests
    ) -> None:
        brain = {"analyst": {"provider": "anthropic", "effort": "high"}}
        (request,) = sent_requests(make_factory(brain).create_analyst_agent())
        assert request["output_config"]["effort"] == "high"

    def test_seed_and_temperature_are_not_forwarded(
        self, make_factory: MakeFactory, sent_requests: SentRequests
    ) -> None:
        brain = {"analyst": {"provider": "anthropic", "seed": 42, "temperature": 0.7}}
        (request,) = sent_requests(make_factory(brain).create_analyst_agent())

        assert "seed" not in request["extra_body"]
        assert "temperature" not in request["extra_body"]
        assert "temperature" not in request

    def test_thinking_is_never_disabled(
        self, make_factory: MakeFactory, sent_requests: SentRequests
    ) -> None:
        agent = make_factory(ALL_ANTHROPIC).create_trader_agent()
        (request,) = sent_requests(agent)

        thinking = request.get("thinking")
        assert not isinstance(thinking, dict) or thinking["type"] == "adaptive"

    def test_server_side_fallback_enabled(
        self, make_factory: MakeFactory, sent_requests: SentRequests
    ) -> None:
        agent = make_factory(ALL_ANTHROPIC).create_analyst_agent()
        (request,) = sent_requests(agent)

        assert "server-side-fallback-2026-07-01" in request["betas"]
        assert request["extra_body"]["fallbacks"] == "default"

    def test_system_prompt_is_cached(
        self, make_factory: MakeFactory, sent_requests: SentRequests
    ) -> None:
        agent = make_factory(ALL_ANTHROPIC).create_analyst_agent()
        (request,) = sent_requests(agent)

        assert request["system"][-1]["cache_control"]["type"] == "ephemeral"

    def test_global_timeout_and_retries(
        self, make_factory: MakeFactory, sent_requests: SentRequests
    ) -> None:
        factory = make_factory(
            {**ALL_ANTHROPIC, "anthropic_max_retries": 1, "request_timeout_s": 90.0}
        )
        agent = factory.create_trader_agent()
        (request,) = sent_requests(agent)

        assert request["timeout"] == 90.0
        assert _model(agent).client.max_retries == 1

    def test_tier_timeout_override_applies(
        self, make_factory: MakeFactory, sent_requests: SentRequests
    ) -> None:
        brain = {"analyst": {"provider": "anthropic", "timeout_s": 12}}
        (request,) = sent_requests(make_factory(brain).create_analyst_agent())

        assert request["timeout"] == 12.0

    def test_output_mode_is_native(self, make_factory: MakeFactory) -> None:
        agent = make_factory(ALL_ANTHROPIC).create_analyst_agent()
        assert isinstance(agent.output_type, NativeOutput)


class TestOpenRouterUnchanged:
    def test_analyst_settings_and_output(self, make_factory: MakeFactory) -> None:
        brain = {"analyst": {"model_id": "test/analyst", "seed": 42}}
        agent = make_factory(brain).create_analyst_agent()

        assert agent.model_settings == {
            "temperature": 0.0,
            "timeout": 120.0,
            "extra_body": {"provider": {"sort": "latency"}},
            "seed": 42,
        }
        assert agent.output_type is AnalystDecisionSchema

    def test_missing_anthropic_key_does_not_break_openrouter_agents(
        self, make_factory: MakeFactory
    ) -> None:
        factory = make_factory({"anthropic_api_key": SecretStr("")})
        assert isinstance(factory.create_analyst_agent().model, OpenAIChatModel)


def _message(**overrides: object) -> BetaMessage:
    fields: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": [],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": BetaUsage(input_tokens=10, output_tokens=5),
    }
    return BetaMessage.model_validate(fields | overrides)


class TestRefusalAndUsage:
    async def test_refusal_raises_content_filter_error(
        self, make_factory: MakeFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = make_factory(ALL_ANTHROPIC).create_analyst_agent()

        async def refuse(**_: object) -> BetaMessage:
            return _message(
                stop_reason="refusal",
                stop_details={
                    "type": "refusal",
                    "category": None,
                    "explanation": "declined",
                },
            )

        monkeypatch.setattr(_model(agent).client.beta.messages, "create", refuse)

        with pytest.raises(ContentFilterError, match="declined"):
            await agent.run("prompt")

    async def test_cache_tokens_are_reported_in_usage(
        self, make_factory: MakeFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = make_factory(ALL_ANTHROPIC).create_analyst_agent()
        decision = {
            "setup_valid": False,
            "direction": "NEUTRAL",
            "confluence_score": 1,
            "key_levels": {},
            "reasoning": "x" * 80,
        }
        text = BetaTextBlock(type="text", text=json.dumps(decision), citations=None)

        async def reply(**_: object) -> BetaMessage:
            return _message(
                content=[text],
                usage=BetaUsage(
                    input_tokens=10,
                    output_tokens=5,
                    cache_read_input_tokens=700,
                    cache_creation_input_tokens=300,
                ),
            )

        monkeypatch.setattr(_model(agent).client.beta.messages, "create", reply)

        result = await agent.run("prompt")

        assert result.usage.cache_read_tokens == 700
        assert result.usage.cache_write_tokens == 300


class TestApiKeyValidation:
    @pytest.fixture
    def app_config(self) -> AppConfig:
        base = AppConfig.from_env()
        openrouter_only = {
            "analyst": AgentModelConfigSchema.model_validate(
                {"provider": "openrouter", "model_id": "anthropic/claude-haiku-4.5"}
            ),
            "trader": AgentModelConfigSchema.model_validate(
                {"provider": "openrouter", "model_id": "openai/gpt-5.4"}
            ),
        }
        brain = base.brain.model_copy(
            update={
                "openrouter_api_key": SecretStr("or-key"),
                "anthropic_api_key": SecretStr(""),
                **openrouter_only,
            }
        )
        return base.model_copy(update={"brain": brain})

    @staticmethod
    def _analyst_on_anthropic(config: AppConfig, key: str) -> AppConfig:
        brain = config.brain.model_copy(
            update={
                "anthropic_api_key": SecretStr(key),
                "analyst": AgentModelConfigSchema(provider=LlmProvider.ANTHROPIC),
            }
        )
        return config.model_copy(update={"brain": brain})

    def test_not_required_when_unused(self, app_config: AppConfig) -> None:
        app_config.validate_for_paper_trading()

    @pytest.mark.parametrize("paper", [True, False])
    def test_required_when_an_agent_uses_anthropic(
        self, app_config: AppConfig, paper: bool
    ) -> None:
        config = self._analyst_on_anthropic(app_config, "")
        validate = (
            config.validate_for_paper_trading if paper else config.validate_for_trading
        )
        with pytest.raises(ValueError, match="KT_ANTHROPIC_API_KEY"):
            validate()

    def test_passes_with_key(self, app_config: AppConfig) -> None:
        self._analyst_on_anthropic(app_config, "an-key").validate_for_paper_trading()

    def test_openrouter_key_not_needed_when_all_agents_on_anthropic(
        self, app_config: AppConfig
    ) -> None:
        brain = BrainConfigSchema.model_validate(
            ALL_ANTHROPIC | {"anthropic_api_key": SecretStr("an-key")}
        )
        external = app_config.external_sources.model_copy(update={"enabled": False})
        config = app_config.model_copy(
            update={"brain": brain, "external_sources": external}
        )
        config.validate_for_paper_trading()

    def test_synthesizer_on_anthropic_requires_key(self, app_config: AppConfig) -> None:
        synth = app_config.external_sources.synthesizer.model_copy(
            update={"provider": LlmProvider.ANTHROPIC}
        )
        external = app_config.external_sources.model_copy(update={"synthesizer": synth})
        config = app_config.model_copy(update={"external_sources": external})
        with pytest.raises(ValueError, match="KT_ANTHROPIC_API_KEY"):
            config.validate_for_paper_trading()


class TestRefusalLogging:
    def test_refusal_logged_as_refused_not_unparseable(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        exc = ContentFilterError("Content filter triggered. Refusal: 'declined'")

        with caplog.at_level(logging.WARNING):
            log_llm_exception(
                "BTCUSDT",
                "trader",
                exc,
                elapsed_ms=900.0,
                body_preview_chars=500,
                exc_message_preview_chars=200,
            )

        (record,) = [r for r in caplog.records if "refused" in r.message]
        assert record.refused is True
        assert "declined" in record.message
        assert not [r for r in caplog.records if "unparseable" in r.message]


class TestAnthropicKeyFromEnv:
    def test_env_var_sets_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KT_ANTHROPIC_API_KEY", "env-key")

        config = AppConfig.from_env()

        assert config.brain.anthropic_api_key.get_secret_value() == "env-key"
        assert "env-key" not in repr(config.brain)
