from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from kavzi_trader.external.sources.deribit_dvol import DeribitDvolSource


def _mock_dvol_response() -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "jsonrpc": "2.0",
        "result": {"index_price": 57.43, "estimated_delivery_price": 57.43},
    }
    return resp


def _mock_book_summary_response() -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "result": [
            {"instrument_name": "BTC-28MAR26-80000-C", "open_interest": 100},
            {"instrument_name": "BTC-28MAR26-80000-P", "open_interest": 60},
            {"instrument_name": "BTC-28MAR26-90000-C", "open_interest": 50},
            {"instrument_name": "BTC-28MAR26-90000-P", "open_interest": 40},
        ],
    }
    return resp


@pytest.mark.asyncio
async def test_fetch_returns_dvol_and_pcr() -> None:
    source = DeribitDvolSource()
    dvol_resp = _mock_dvol_response()
    book_resp = _mock_book_summary_response()

    async def mock_get(url: str, params: dict[str, str] | None = None) -> Mock:
        if "get_index_price" in url:
            return dvol_resp
        return book_resp

    source._client = Mock()
    source._client.get = AsyncMock(side_effect=mock_get)

    result = await source.fetch()
    assert result is not None
    assert result.dvol_index == Decimal("57.43")
    # PCR = (60 + 40) / (100 + 50) = 100 / 150 = 0.666...
    expected_pcr = Decimal(100) / Decimal(150)
    assert result.btc_put_call_ratio == expected_pcr
    assert result.fetched_at is not None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_error() -> None:
    source = DeribitDvolSource()
    source._client = Mock()
    source._client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    result = await source.fetch()
    assert result is None


@pytest.mark.asyncio
async def test_pcr_zero_call_oi() -> None:
    source = DeribitDvolSource()
    dvol_resp = _mock_dvol_response()
    no_calls_resp = Mock()
    no_calls_resp.raise_for_status = Mock()
    no_calls_resp.json.return_value = {
        "result": [
            {"instrument_name": "BTC-28MAR26-80000-P", "open_interest": 100},
        ],
    }

    async def mock_get(url: str, params: dict[str, str] | None = None) -> Mock:
        if "get_index_price" in url:
            return dvol_resp
        return no_calls_resp

    source._client = Mock()
    source._client.get = AsyncMock(side_effect=mock_get)
    result = await source.fetch()
    assert result is not None
    assert result.btc_put_call_ratio == Decimal(0)


def test_source_name() -> None:
    assert DeribitDvolSource().name == "deribit_dvol"
