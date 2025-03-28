"""
Tests for common API interfaces.

This module contains tests for the common API interfaces, base classes, and utilities.
"""

import pytest
import requests
import responses

from src.api.common.base import BaseExchangeAPI
from src.api.common.client import APIClient
from src.api.common.exceptions import (
    APIError,
    AuthenticationError,
    ExchangeError,
    RateLimitError,
    RequestError,
)
from src.api.common.models import OrderSide, OrderStatus, OrderType, TimeInForce


class TestExchangeAPI(APIClient, BaseExchangeAPI):
    """Test implementation of BaseExchangeAPI for testing."""

    def __init__(self, api_key=None, api_secret=None, **kwargs):
        super().__init__(api_key=api_key, api_secret=api_secret, **kwargs)
        self.base_url = "https://api.test-exchange.com"

    def ping(self):
        return self._get("/ping")

    def get_server_time(self):
        return self._parse_datetime(self._get("/time")["serverTime"])

    def get_exchange_info(self):
        return self._get("/exchangeInfo")

    def get_symbol_info(self, symbol):
        # Implementation for testing
        pass

    def get_orderbook(self, symbol, **kwargs):
        # Implementation for testing
        pass

    def get_recent_trades(self, symbol, **kwargs):
        # Implementation for testing
        pass

    def get_historical_trades(self, symbol, **kwargs):
        # Implementation for testing
        pass

    def get_klines(self, symbol, interval, **kwargs):
        # Implementation for testing
        pass

    def get_ticker(self, symbol=None):
        # Implementation for testing
        pass

    def get_all_tickers(self):
        # Implementation for testing
        pass

    def get_price(self, symbol=None):
        response = self._get(
            "/ticker/price",
            params={"symbol": symbol} if symbol else None,
        )
        if symbol:
            return float(response["price"])
        return {item["symbol"]: float(item["price"]) for item in response}

    def get_account_info(self):
        return self._get("/account", signed=True)

    def get_asset_balance(self, asset):
        account = self.get_account_info()
        for balance in account["balances"]:
            if balance["asset"] == asset:
                return balance
        return None

    def create_order(self, **kwargs):
        # Implementation for testing
        pass

    def get_order(self, symbol, **kwargs):
        # Implementation for testing
        pass

    def cancel_order(self, symbol, **kwargs):
        # Implementation for testing
        pass

    def get_open_orders(self, symbol=None):
        # Implementation for testing
        pass


@pytest.fixture()
def client():
    """Create a test client for testing."""
    return TestExchangeAPI(api_key="test_key", api_secret="test_secret")


class TestBaseAPI:
    """Tests for the base API classes and interfaces."""

    @responses.activate
    def test_get_request(self, client):
        """Test basic GET request functionality."""
        # Mock the response
        responses.add(
            responses.GET,
            "https://api.test-exchange.com/ping",
            json={},
            status=200,
        )

        # Call the API
        result = client.ping()

        # Verify the result
        assert result == {}
        assert len(responses.calls) == 1

    @responses.activate
    def test_rate_limit_exceeded(self, client):
        """Test rate limit exceeded handling."""
        # Mock the response
        responses.add(
            responses.GET,
            "https://api.test-exchange.com/time",
            json={"code": -1003, "msg": "Rate limit exceeded"},
            status=429,
        )

        # Test that rate limit error is raised
        with pytest.raises(RateLimitError):
            client.get_server_time()

    @responses.activate
    def test_authentication_error(self, client):
        """Test authentication error handling."""
        # Mock the response
        responses.add(
            responses.GET,
            "https://api.test-exchange.com/account",
            json={"code": -2015, "msg": "Invalid API-key, IP, or permissions"},
            status=401,
        )

        # Test that authentication error is raised
        with pytest.raises(AuthenticationError):
            client.get_account_info()

    @responses.activate
    def test_request_error(self, client):
        """Test request error handling."""
        # Mock the response to fail with a connection error
        responses.add(
            responses.GET,
            "https://api.test-exchange.com/exchangeInfo",
            body=requests.exceptions.ConnectionError("Connection refused"),
        )

        # Test that request error is raised
        with pytest.raises(RequestError):
            client.get_exchange_info()

    @responses.activate
    def test_get_price(self, client):
        """Test get price functionality."""
        # Mock the response for a single symbol
        responses.add(
            responses.GET,
            "https://api.test-exchange.com/ticker/price",
            json={"symbol": "BTCUSDT", "price": "20000.00"},
            status=200,
            match=[responses.matchers.query_param_matcher({"symbol": "BTCUSDT"})],
        )

        # Mock the response for all symbols
        responses.add(
            responses.GET,
            "https://api.test-exchange.com/ticker/price",
            json=[
                {"symbol": "BTCUSDT", "price": "20000.00"},
                {"symbol": "ETHUSDT", "price": "1500.00"},
            ],
            status=200,
            match=[responses.matchers.query_param_matcher({})],
        )

        # Test getting price for a single symbol
        price = client.get_price("BTCUSDT")
        assert price == 20000.00

        # Test getting all prices
        prices = client.get_price()
        assert isinstance(prices, dict)
        assert prices["BTCUSDT"] == 20000.00
        assert prices["ETHUSDT"] == 1500.00

    @responses.activate
    def test_retry_logic(self, client):
        """Test request retry logic."""
        # Override the retry settings for testing
        client.max_retries = 2
        client.retry_wait = 0.01

        # Mock responses that will fail and then succeed
        responses.add(
            responses.GET,
            "https://api.test-exchange.com/ping",
            json={"code": -1000, "msg": "Server error"},
            status=500,
        )

        responses.add(
            responses.GET,
            "https://api.test-exchange.com/ping",
            json={},
            status=200,
        )

        # Call the API, should retry and succeed
        result = client.ping()

        # Verify the result
        assert result == {}
        assert len(responses.calls) == 2


class TestExceptions:
    """Tests for the exception hierarchy."""

    def test_exception_hierarchy(self):
        """Test that the exception hierarchy is correctly defined."""
        assert issubclass(AuthenticationError, APIError)
        assert issubclass(RateLimitError, APIError)
        assert issubclass(RequestError, APIError)
        assert issubclass(ExchangeError, APIError)

    def test_exception_messages(self):
        """Test exception messages and representations."""
        error = APIError("Test error")
        assert str(error) == "Test error"

        auth_error = AuthenticationError("Invalid API key")
        assert str(auth_error) == "Authentication Error: Invalid API key"

        rate_limit_error = RateLimitError("Rate limit exceeded")
        assert str(rate_limit_error) == "Rate Limit Error: Rate limit exceeded"

        request_error = RequestError("Connection refused")
        assert str(request_error) == "Request Error: Connection refused"

        exchange_error = ExchangeError("Unknown symbol", code=1001)
        assert str(exchange_error) == "Exchange Error (1001): Unknown symbol"


class TestModels:
    """Tests for the data models."""

    def test_order_enums(self):
        """Test enumeration models."""
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"

        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.MARKET.value == "MARKET"

        assert OrderStatus.NEW.value == "NEW"
        assert OrderStatus.FILLED.value == "FILLED"

        assert TimeInForce.GTC.value == "GTC"
        assert TimeInForce.IOC.value == "IOC"
