import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.api.binance.websocket.client import BinanceWebsocketClient
from kavzi_trader.api.common.exceptions import APIError
from kavzi_trader.orchestrator.loops.ingest import DataIngestLoop
from kavzi_trader.orchestrator.providers.live_stream_manager import LiveStreamManager
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.orchestrator.providers.stream_disconnected_error import (
    StreamDisconnectedError,
)

TEST_TIMEOUT_S = 3


def _manager(ws_client: MagicMock) -> LiveStreamManager:
    return LiveStreamManager(
        ws_client=cast("BinanceWebsocketClient", ws_client),
        cache=MagicMock(spec=MarketDataCache),
        symbols=["BTCUSDT"],
        interval="15m",
    )


def _ws_client(*, connected: bool) -> MagicMock:
    ws_client = MagicMock()
    ws_client.start = AsyncMock()
    ws_client.stop = AsyncMock()
    ws_client.subscribe_kline_stream = AsyncMock()
    ws_client.subscribe_ticker_stream = AsyncMock()
    ws_client.is_connected.return_value = connected
    return ws_client


class TestFatalErrors:
    async def test_start_raises_when_the_feed_dies(self) -> None:
        ws_client = _ws_client(connected=False)
        manager = _manager(ws_client)
        manager.handle_ws_error(APIError("Recv loop error for btcusdt@kline_15m"))

        async with asyncio.timeout(TEST_TIMEOUT_S):
            with pytest.raises(StreamDisconnectedError, match="Recv loop error"):
                await manager.start()

        ws_client.stop.assert_awaited_once()

    async def test_start_raises_without_a_reported_error(self) -> None:
        manager = _manager(_ws_client(connected=False))

        async with asyncio.timeout(TEST_TIMEOUT_S):
            with pytest.raises(StreamDisconnectedError):
                await manager.start()

    async def test_error_is_logged_with_stream_context(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        manager = _manager(_ws_client(connected=True))

        with caplog.at_level("ERROR"):
            manager.handle_ws_error(APIError("boom"))

        record = caplog.records[-1]
        assert "boom" in record.getMessage()
        assert record.__dict__["interval"] == "15m"
        assert record.__dict__["symbols"] == ["BTCUSDT"]


async def test_ingest_loop_surfaces_stream_failure_to_supervisor() -> None:
    manager = _manager(_ws_client(connected=False))
    loop = DataIngestLoop(manager)

    async with asyncio.timeout(TEST_TIMEOUT_S):
        with pytest.raises(StreamDisconnectedError):
            await loop.run()
