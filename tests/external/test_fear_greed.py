from unittest.mock import AsyncMock, Mock

import pytest

from kavzi_trader.external.sources.fear_greed import FearGreedSource


def _mock_response(value: int = 35, classification: str = "Fear") -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "data": [
            {
                "value": str(value),
                "value_classification": classification,
                "timestamp": "1711584000",
            },
        ],
    }
    return resp


@pytest.mark.asyncio
async def test_fetch_returns_parsed_data() -> None:
    source = FearGreedSource()
    source._client = Mock()
    source._client.get = AsyncMock(return_value=_mock_response(35, "Fear"))
    result = await source.fetch()
    assert result is not None
    assert result.value == 35
    assert result.classification == "Fear"
    assert result.fetched_at is not None


@pytest.mark.asyncio
async def test_fetch_empty_data_returns_none() -> None:
    source = FearGreedSource()
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"data": []}
    source._client = Mock()
    source._client.get = AsyncMock(return_value=resp)
    result = await source.fetch()
    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_error() -> None:
    source = FearGreedSource()
    source._client = Mock()
    source._client.get = AsyncMock(side_effect=RuntimeError("timeout"))
    result = await source.fetch()
    assert result is None


def test_source_name() -> None:
    assert FearGreedSource().name == "fear_greed"
