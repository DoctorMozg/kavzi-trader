"""Market data must come from USDT-M futures endpoints, not spot."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.paper.exchange import PaperExchangeClient

_KLINE_ROW = [
    1_700_000_000_000,
    "100.0",
    "110.0",
    "90.0",
    "105.0",
    "12.5",
    1_700_000_899_999,
    "1300.0",
    42,
    "6.0",
    "620.0",
    "0",
]

_FUTURES_TICKER = {
    "symbol": "BTCUSDT",
    "priceChange": "-94.99",
    "priceChangePercent": "-95.960",
    "weightedAvgPrice": "0.29628482",
    "lastPrice": "4.00000200",
    "lastQty": "200.00000000",
    "openPrice": "99.00000000",
    "highPrice": "100.00000000",
    "lowPrice": "0.10000000",
    "volume": "8913.30000000",
    "quoteVolume": "15.30000000",
    "openTime": 1_499_783_499_040,
    "closeTime": 1_499_869_899_040,
    "firstId": 28385,
    "lastId": 28460,
    "count": 76,
}


@pytest_asyncio.fixture
async def client() -> BinanceClient:
    binance_client = BinanceClient()
    # Close the real aiohttp session before swapping in the mock
    await binance_client.client.close_connection()
    binance_client.client = AsyncMock()
    return binance_client


class TestFuturesMarketData:
    async def test_get_klines_uses_futures_endpoint(
        self,
        client: BinanceClient,
    ) -> None:
        client.client.futures_klines.return_value = [_KLINE_ROW]

        candles = await client.get_klines("BTCUSDT", "15m", limit=1)

        client.client.futures_klines.assert_awaited_once_with(
            symbol="BTCUSDT",
            interval="15m",
            limit=1,
        )
        client.client.get_klines.assert_not_called()
        assert candles[0].close_price == Decimal("105.0")
        assert candles[0].trades_count == 42

    async def test_get_ticker_uses_futures_endpoint(
        self,
        client: BinanceClient,
    ) -> None:
        client.client.futures_ticker.return_value = _FUTURES_TICKER

        ticker = await client.get_ticker("BTCUSDT")

        client.client.futures_ticker.assert_awaited_once_with(symbol="BTCUSDT")
        client.client.get_ticker.assert_not_called()
        assert ticker.last_price == Decimal("4.00000200")
        # Futures 24h ticker has no bid/ask or previous close fields
        assert ticker.bid_price is None
        assert ticker.prev_close_price is None

    async def test_paper_client_uses_futures_ticker(self) -> None:
        with patch("kavzi_trader.api.binance.client.BinanceAPIClient"):
            paper = PaperExchangeClient()
        paper.client = MagicMock(
            futures_ticker=AsyncMock(return_value=_FUTURES_TICKER),
        )

        ticker = await paper.get_ticker("BTCUSDT")

        paper.client.futures_ticker.assert_awaited_once_with(symbol="BTCUSDT")
        assert paper._last_prices["BTCUSDT"] == ticker.last_price
