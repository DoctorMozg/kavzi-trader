from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from kavzi_trader.external.schemas import (
    DeribitDvolDataSchema,
    ExternalDataSnapshotSchema,
    FearGreedDataSchema,
    SentimentSummarySchema,
)
from kavzi_trader.external.synthesizer import (
    SentimentSynthesizer,
    _format_snapshot_for_prompt,
)


def _make_full_snapshot() -> ExternalDataSnapshotSchema:
    now = datetime.now(UTC)
    return ExternalDataSnapshotSchema(
        deribit_dvol=DeribitDvolDataSchema(
            dvol_index=Decimal("55.0"),
            btc_put_call_ratio=Decimal("0.65"),
            fetched_at=now,
        ),
        fear_greed=FearGreedDataSchema(
            value=25,
            classification="Extreme Fear",
            fetched_at=now,
        ),
    )


def _make_summary() -> SentimentSummarySchema:
    return SentimentSummarySchema(
        summary="Options volatility elevated. Fear & Greed at extreme fear.",
        sentiment_bias="BEARISH",
        confidence_adjustment=Decimal("-0.05"),
        generated_at=datetime.now(UTC),
    )


def test_format_snapshot_with_deribit_and_fgi() -> None:
    text = _format_snapshot_for_prompt(_make_full_snapshot())
    assert "DERIBIT OPTIONS:" in text
    assert "55.0" in text
    assert "0.650" in text
    assert "FEAR & GREED INDEX:" in text
    assert "25/100" in text
    assert "Extreme Fear" in text
    assert "NEWS SENTIMENT: unavailable" in text


def test_format_snapshot_all_unavailable() -> None:
    text = _format_snapshot_for_prompt(ExternalDataSnapshotSchema())
    assert "DERIBIT OPTIONS: unavailable" in text
    assert "FEAR & GREED INDEX: unavailable" in text
    assert "NEWS SENTIMENT: unavailable" in text


@pytest.mark.asyncio
async def test_synthesize_empty_snapshot_returns_neutral() -> None:
    agent = Mock()
    prompt_loader = Mock()
    synth = SentimentSynthesizer(agent, prompt_loader)
    result = await synth.synthesize(ExternalDataSnapshotSchema())
    assert result is not None
    assert result.sentiment_bias == "NEUTRAL"
    assert result.confidence_adjustment == Decimal(0)


@pytest.mark.asyncio
async def test_synthesize_calls_agent() -> None:
    summary = _make_summary()
    agent_result = Mock()
    agent_result.output = summary
    agent = Mock()
    agent.run = AsyncMock(return_value=agent_result)
    prompt_loader = Mock()
    prompt_loader.render_user_prompt.return_value = "test prompt"
    synth = SentimentSynthesizer(agent, prompt_loader)
    result = await synth.synthesize(_make_full_snapshot())
    assert result is not None
    assert result.sentiment_bias == "BEARISH"
    agent.run.assert_awaited_once_with("test prompt")
    prompt_loader.render_user_prompt.assert_called_once()


@pytest.mark.asyncio
async def test_synthesize_returns_none_on_agent_error() -> None:
    agent = Mock()
    agent.run = AsyncMock(side_effect=RuntimeError("LLM timeout"))
    prompt_loader = Mock()
    prompt_loader.render_user_prompt.return_value = "test prompt"
    synth = SentimentSynthesizer(agent, prompt_loader)
    result = await synth.synthesize(_make_full_snapshot())
    assert result is None
