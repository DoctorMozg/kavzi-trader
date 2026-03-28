from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from kavzi_trader.external.sources.cryptopanic import CryptoPanicSource


def _mock_response() -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "results": [
            {
                "title": "Bitcoin surges past 100k",
                "votes": {"positive": 10, "negative": 2},
            },
            {
                "title": "Ethereum upgrade delayed",
                "votes": {"positive": 3, "negative": 8},
            },
            {
                "title": "Market consolidation continues",
                "votes": {"positive": 5, "negative": 5},
            },
        ],
    }
    return resp


@pytest.mark.asyncio
async def test_fetch_returns_parsed_data() -> None:
    source = CryptoPanicSource(api_key="test-key", max_results=20)
    source._client = Mock()
    source._client.get = AsyncMock(return_value=_mock_response())
    result = await source.fetch()
    assert result is not None
    assert result.bullish_count == 1
    assert result.bearish_count == 1
    assert result.neutral_count == 1
    assert len(result.top_headlines) == 3
    assert result.top_headlines[0] == "Bitcoin surges past 100k"
    assert result.fetched_at is not None


@pytest.mark.asyncio
async def test_sentiment_score_calculation() -> None:
    source = CryptoPanicSource(api_key="test-key")
    source._client = Mock()
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "results": [
            {"title": "Bullish 1", "votes": {"positive": 10, "negative": 1}},
            {"title": "Bullish 2", "votes": {"positive": 8, "negative": 2}},
            {"title": "Bearish 1", "votes": {"positive": 1, "negative": 10}},
        ],
    }
    source._client.get = AsyncMock(return_value=resp)
    result = await source.fetch()
    assert result is not None
    # 2 bullish - 1 bearish = 1, total = 3 → score = 1/3
    expected = Decimal(str(1 / 3))
    assert result.sentiment_score == expected


@pytest.mark.asyncio
async def test_max_results_limits_posts() -> None:
    source = CryptoPanicSource(api_key="test-key", max_results=2)
    source._client = Mock()
    source._client.get = AsyncMock(return_value=_mock_response())
    result = await source.fetch()
    assert result is not None
    # 3 posts but max_results=2 so only 2 processed
    total = result.bullish_count + result.bearish_count + result.neutral_count
    assert total == 2


@pytest.mark.asyncio
async def test_fetch_returns_none_on_error() -> None:
    source = CryptoPanicSource(api_key="test-key")
    source._client = Mock()
    source._client.get = AsyncMock(side_effect=RuntimeError("API error"))
    result = await source.fetch()
    assert result is None


@pytest.mark.asyncio
async def test_headlines_capped_at_max_headlines() -> None:
    source = CryptoPanicSource(api_key="test-key", max_results=10, max_headlines=5)
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "results": [
            {"title": f"Headline {i}", "votes": {"positive": 1, "negative": 0}}
            for i in range(8)
        ],
    }
    source._client = Mock()
    source._client.get = AsyncMock(return_value=resp)
    result = await source.fetch()
    assert result is not None
    assert len(result.top_headlines) == 5


@pytest.mark.asyncio
async def test_custom_max_headlines() -> None:
    source = CryptoPanicSource(api_key="test-key", max_results=10, max_headlines=3)
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "results": [
            {"title": f"Headline {i}", "votes": {"positive": 1, "negative": 0}}
            for i in range(8)
        ],
    }
    source._client = Mock()
    source._client.get = AsyncMock(return_value=resp)
    result = await source.fetch()
    assert result is not None
    assert len(result.top_headlines) == 3


def test_source_name() -> None:
    assert CryptoPanicSource(api_key="k").name == "cryptopanic"
