import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.orchestrator.loops.ingest import DataIngestLoop
from kavzi_trader.orchestrator.loops.order_flow import OrderFlowLoop

TEST_TIMEOUT_S = 2


async def _run_until(loop: OrderFlowLoop, fetcher: AsyncMock, calls: int) -> None:
    task = asyncio.create_task(loop.run())
    try:
        async with asyncio.timeout(TEST_TIMEOUT_S):
            while fetcher.fetch.await_count < calls:
                await asyncio.sleep(0)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestDataIngestLoop:
    async def test_run_starts_the_stream_manager_once(self) -> None:
        stream_manager = AsyncMock()

        await DataIngestLoop(stream_manager).run()

        stream_manager.start.assert_awaited_once()

    async def test_stream_failure_propagates_to_the_supervisor(self) -> None:
        stream_manager = AsyncMock()
        stream_manager.start.side_effect = ConnectionError("feed lost")

        with pytest.raises(ConnectionError, match="feed lost"):
            await DataIngestLoop(stream_manager).run()


class TestOrderFlowLoopWarmUp:
    async def test_warm_up_fetches_once(self) -> None:
        fetcher = AsyncMock()

        await OrderFlowLoop(fetcher, interval_s=60).warm_up()

        fetcher.fetch.assert_awaited_once()

    async def test_warm_up_failure_is_logged_not_raised(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        fetcher = AsyncMock()
        fetcher.fetch.side_effect = RuntimeError("api down")

        with caplog.at_level(logging.ERROR):
            await OrderFlowLoop(fetcher, interval_s=60).warm_up()

        record = caplog.records[-1]
        assert "warm-up failed" in record.getMessage()
        assert record.__dict__["phase"] == "warm-up"


class TestOrderFlowLoopRun:
    async def test_run_fetches_every_cycle(self) -> None:
        fetcher = AsyncMock()

        await _run_until(OrderFlowLoop(fetcher, interval_s=0), fetcher, calls=3)

        assert fetcher.fetch.await_count >= 3

    async def test_fetch_error_does_not_stop_later_cycles(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        fetcher = AsyncMock()
        fetcher.fetch.side_effect = [RuntimeError("api down"), None, None]

        with caplog.at_level(logging.ERROR):
            await _run_until(OrderFlowLoop(fetcher, interval_s=0), fetcher, calls=3)

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 1
        assert errors[0].__dict__["cycle"] == 1
        assert errors[0].__dict__["phase"] == "steady"
