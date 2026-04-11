import logging
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from kavzi_trader.external.sources import ccdata_news as ccdata_news_module
from kavzi_trader.external.sources.ccdata_news import CCDataNewsSource


@pytest.fixture(autouse=True)
def _fast_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace asyncio.sleep inside ccdata_news with a no-op.

    Keeps retry-behavior tests fast and prevents any other test that
    triggers the retry path from paying the real backoff cost.
    """

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ccdata_news_module.asyncio, "sleep", _no_sleep)


def _mock_response() -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "Data": [
            {
                "TITLE": "Bitcoin surges past 100k",
                "SENTIMENT": "POSITIVE",
                "UPVOTES": 10,
                "DOWNVOTES": 2,
            },
            {
                "TITLE": "Ethereum upgrade delayed",
                "SENTIMENT": "NEGATIVE",
                "UPVOTES": 3,
                "DOWNVOTES": 8,
            },
            {
                "TITLE": "Market consolidation continues",
                "SENTIMENT": "NEUTRAL",
                "UPVOTES": 5,
                "DOWNVOTES": 5,
            },
        ],
    }
    return resp


@pytest.mark.asyncio
async def test_fetch_returns_parsed_data() -> None:
    source = CCDataNewsSource(max_results=20)
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
    source = CCDataNewsSource()
    source._client = Mock()
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "Data": [
            {"TITLE": "Bullish 1", "SENTIMENT": "POSITIVE"},
            {"TITLE": "Bullish 2", "SENTIMENT": "POSITIVE"},
            {"TITLE": "Bearish 1", "SENTIMENT": "NEGATIVE"},
        ],
    }
    source._client.get = AsyncMock(return_value=resp)
    result = await source.fetch()
    assert result is not None
    # 2 bullish - 1 bearish = 1, total = 3 -> score = 1/3
    expected = Decimal(str(1 / 3))
    assert result.sentiment_score == expected


@pytest.mark.asyncio
async def test_fetch_returns_none_on_error() -> None:
    source = CCDataNewsSource()
    source._client = Mock()
    source._client.get = AsyncMock(side_effect=RuntimeError("API error"))
    result = await source.fetch()
    assert result is None


@pytest.mark.asyncio
async def test_fetch_retries_on_transient_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """First two attempts fail, third succeeds — retry path must recover."""
    source = CCDataNewsSource()
    source._client = Mock()
    source._client.get = AsyncMock(
        side_effect=[
            RuntimeError("transient boom 1"),
            RuntimeError("transient boom 2"),
            _mock_response(),
        ]
    )

    with caplog.at_level(logging.WARNING, logger=ccdata_news_module.logger.name):
        result = await source.fetch()

    assert result is not None
    assert result.bullish_count == 1
    assert result.bearish_count == 1
    assert source._client.get.await_count == 3
    retry_warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "CCData news fetch attempt" in record.getMessage()
    ]
    assert len(retry_warnings) == 2


@pytest.mark.asyncio
async def test_fetch_returns_none_after_max_retries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """All three attempts fail — must return None and log exactly once."""
    source = CCDataNewsSource()
    source._client = Mock()
    source._client.get = AsyncMock(side_effect=RuntimeError("persistent boom"))

    with caplog.at_level(logging.WARNING, logger=ccdata_news_module.logger.name):
        result = await source.fetch()

    assert result is None
    assert source._client.get.await_count == 3
    exception_records = [
        record for record in caplog.records if record.levelno == logging.ERROR
    ]
    assert len(exception_records) == 1
    assert "after 3 attempts" in exception_records[0].getMessage()


@pytest.mark.asyncio
async def test_headlines_capped_at_max_headlines() -> None:
    source = CCDataNewsSource(max_results=10, max_headlines=5)
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "Data": [{"TITLE": f"Headline {i}", "SENTIMENT": "POSITIVE"} for i in range(8)],
    }
    source._client = Mock()
    source._client.get = AsyncMock(return_value=resp)
    result = await source.fetch()
    assert result is not None
    assert len(result.top_headlines) == 5


@pytest.mark.asyncio
async def test_custom_max_headlines() -> None:
    source = CCDataNewsSource(max_results=10, max_headlines=3)
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "Data": [{"TITLE": f"Headline {i}", "SENTIMENT": "POSITIVE"} for i in range(8)],
    }
    source._client = Mock()
    source._client.get = AsyncMock(return_value=resp)
    result = await source.fetch()
    assert result is not None
    assert len(result.top_headlines) == 3


def test_source_name() -> None:
    assert CCDataNewsSource().name == "ccdata_news"


@pytest.mark.asyncio
async def test_missing_sentiment_defaults_to_neutral() -> None:
    """Articles without SENTIMENT field should count as neutral."""
    source = CCDataNewsSource()
    source._client = Mock()
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "Data": [
            {"TITLE": "No sentiment field"},
            {"TITLE": "Also missing", "SENTIMENT": ""},
        ],
    }
    source._client.get = AsyncMock(return_value=resp)
    result = await source.fetch()
    assert result is not None
    assert result.neutral_count == 2
    assert result.bullish_count == 0
    assert result.bearish_count == 0


@pytest.mark.asyncio
async def test_empty_data_array() -> None:
    """Empty Data array should return zero counts."""
    source = CCDataNewsSource()
    source._client = Mock()
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"Data": []}
    source._client.get = AsyncMock(return_value=resp)
    result = await source.fetch()
    assert result is not None
    assert result.bullish_count == 0
    assert result.bearish_count == 0
    assert result.neutral_count == 0
    assert result.sentiment_score == Decimal(0)
    assert result.top_headlines == []
