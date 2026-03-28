from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel

from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.external.loop import ExternalSentimentLoop
from kavzi_trader.external.schemas import (
    DeribitDvolDataSchema,
    FearGreedDataSchema,
    SentimentSummarySchema,
)


def _make_deribit_source() -> Mock:
    source = Mock()
    source.name = "deribit_dvol"
    source.fetch = AsyncMock(
        return_value=DeribitDvolDataSchema(
            dvol_index=Decimal("55.0"),
            btc_put_call_ratio=Decimal("0.65"),
            fetched_at=datetime.now(UTC),
        ),
    )
    return source


def _make_fgi_source() -> Mock:
    source = Mock()
    source.name = "fear_greed"
    source.fetch = AsyncMock(
        return_value=FearGreedDataSchema(
            value=30,
            classification="Fear",
            fetched_at=datetime.now(UTC),
        ),
    )
    return source


def _make_summary() -> SentimentSummarySchema:
    return SentimentSummarySchema(
        summary="Market shows fear with elevated volatility.",
        sentiment_bias="BEARISH",
        confidence_adjustment=Decimal("-0.05"),
    )


def _make_loop(**kwargs: Any) -> ExternalSentimentLoop:
    """Create loop with type-ignored Mock sources."""
    return ExternalSentimentLoop(**kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cycle_fetches_and_caches_snapshot() -> None:
    cache = ExternalDataCache()
    loop = _make_loop(
        sources=[_make_deribit_source(), _make_fgi_source()],
        synthesizer=None,
        cache=cache,
        interval_s=60,
    )
    await loop._cycle()
    snapshot = cache.get_snapshot()
    assert not snapshot.is_empty()
    assert snapshot.deribit_dvol is not None
    assert snapshot.fear_greed is not None


@pytest.mark.asyncio
async def test_cycle_calls_synthesizer() -> None:
    cache = ExternalDataCache()
    synthesizer = Mock()
    summary = _make_summary()
    synthesizer.synthesize = AsyncMock(return_value=summary)
    loop = _make_loop(
        sources=[_make_deribit_source()],
        synthesizer=synthesizer,
        cache=cache,
        interval_s=60,
    )
    await loop._cycle()
    synthesizer.synthesize.assert_awaited_once()
    retrieved = cache.get_sentiment_summary()
    assert retrieved is not None
    assert retrieved.sentiment_bias == "BEARISH"


@pytest.mark.asyncio
async def test_cycle_skips_synthesis_on_empty_snapshot() -> None:
    cache = ExternalDataCache()
    source = Mock()
    source.name = "deribit_dvol"
    source.fetch = AsyncMock(return_value=None)
    synthesizer = Mock()
    synthesizer.synthesize = AsyncMock()
    loop = _make_loop(
        sources=[source],
        synthesizer=synthesizer,
        cache=cache,
        interval_s=60,
    )
    await loop._cycle()
    synthesizer.synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_failure_does_not_block_others() -> None:
    cache = ExternalDataCache()
    failing_source = Mock()
    failing_source.name = "deribit_dvol"
    failing_source.fetch = AsyncMock(side_effect=RuntimeError("network error"))
    loop = _make_loop(
        sources=[failing_source, _make_fgi_source()],
        synthesizer=None,
        cache=cache,
        interval_s=60,
    )
    await loop._cycle()
    snapshot = cache.get_snapshot()
    assert snapshot.deribit_dvol is None
    assert snapshot.fear_greed is not None


@pytest.mark.asyncio
async def test_synthesizer_failure_keeps_stale_summary() -> None:
    cache = ExternalDataCache()
    old_summary = _make_summary()
    cache.set_sentiment_summary(old_summary)
    synthesizer = Mock()
    synthesizer.synthesize = AsyncMock(side_effect=RuntimeError("LLM error"))
    loop = _make_loop(
        sources=[_make_deribit_source()],
        synthesizer=synthesizer,
        cache=cache,
        interval_s=60,
    )
    await loop._cycle()
    # Stale summary should still be present
    assert cache.get_sentiment_summary() is old_summary


@pytest.mark.asyncio
async def test_typed_get_returns_correct_type() -> None:
    data: dict[str, BaseModel] = {
        "deribit_dvol": DeribitDvolDataSchema(
            dvol_index=Decimal(50),
            btc_put_call_ratio=Decimal("0.5"),
            fetched_at=datetime.now(UTC),
        ),
    }
    result = ExternalSentimentLoop._typed_get(
        data,
        "deribit_dvol",
        DeribitDvolDataSchema,
    )
    assert result is not None
    assert isinstance(result, DeribitDvolDataSchema)


@pytest.mark.asyncio
async def test_typed_get_returns_none_for_missing_key() -> None:
    result = ExternalSentimentLoop._typed_get(
        {},
        "deribit_dvol",
        DeribitDvolDataSchema,
    )
    assert result is None


@pytest.mark.asyncio
async def test_typed_get_returns_none_for_wrong_type() -> None:
    data: dict[str, BaseModel] = {
        "deribit_dvol": FearGreedDataSchema(
            value=30,
            classification="Fear",
            fetched_at=datetime.now(UTC),
        ),
    }
    result = ExternalSentimentLoop._typed_get(
        data,
        "deribit_dvol",
        DeribitDvolDataSchema,
    )
    assert result is None
