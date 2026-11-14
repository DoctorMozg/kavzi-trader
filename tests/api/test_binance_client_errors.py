"""Offline tests for Binance exception mapping in BinanceClient."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from binance.exceptions import BinanceAPIException, BinanceRequestException

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.exceptions import (
    AuthenticationError,
    ExchangeError,
    RateLimitError,
    RequestError,
)


def _api_exception(code: int, msg: str = "boom") -> BinanceAPIException:
    response = MagicMock()
    response.status_code = 400
    return BinanceAPIException(
        response,
        400,
        json.dumps({"code": code, "msg": msg}),
    )


@pytest_asyncio.fixture
async def client() -> BinanceClient:
    binance_client = BinanceClient()
    # Close the real aiohttp session before swapping in the mock
    await binance_client.client.close_connection()
    binance_client.client = AsyncMock()
    return binance_client


class TestHandleApiErrors:
    async def test_unknown_order_maps_to_exchange_error_with_code(
        self,
        client: BinanceClient,
    ) -> None:
        client.client.futures_cancel_order.side_effect = _api_exception(-2011)

        with pytest.raises(ExchangeError) as exc_info:
            await client.cancel_order(symbol="BTCUSDT", order_id=1)

        assert exc_info.value.code == -2011

    async def test_invalid_api_key_maps_to_authentication_error(
        self,
        client: BinanceClient,
    ) -> None:
        client.client.ping.side_effect = _api_exception(-2015)

        with pytest.raises(AuthenticationError):
            await client.ping()

    async def test_too_many_requests_maps_to_rate_limit_error(
        self,
        client: BinanceClient,
    ) -> None:
        client.client.ping.side_effect = _api_exception(-1003, "Too many requests")

        with pytest.raises(RateLimitError):
            await client.ping()

    async def test_request_exception_maps_to_request_error(
        self,
        client: BinanceClient,
    ) -> None:
        client.client.ping.side_effect = BinanceRequestException("bad payload")

        with pytest.raises(RequestError):
            await client.ping()

    async def test_non_binance_errors_propagate_unchanged(
        self,
        client: BinanceClient,
    ) -> None:
        with pytest.raises(ValueError, match="Either order_id"):
            await client.get_order(symbol="BTCUSDT")

    async def test_success_returns_result(self, client: BinanceClient) -> None:
        assert await client.ping() is True
