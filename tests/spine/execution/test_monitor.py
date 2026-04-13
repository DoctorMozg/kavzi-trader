from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.models import OrderStatus
from kavzi_trader.spine.execution import monitor as monitor_module
from kavzi_trader.spine.execution.monitor import OrderMonitor


@pytest.mark.asyncio
async def test_monitor_returns_filled_order(filled_order_response) -> None:
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(return_value=filled_order_response)
    monitor = OrderMonitor(exchange=exchange, timeout_s=1)

    result = await monitor.wait_for_completion("BTCUSDT", 123)

    assert result is not None
    assert result.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_monitor_backoff_grows_exponentially_and_caps(
    filled_order_response,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exponential backoff on poll exceptions, capped at 30s, reset on success."""
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(monitor_module.asyncio, "sleep", fake_sleep)

    # Seven failures then success, so the cap engages (2^5=32 -> 30, 2^6=64 -> 30).
    side_effects: list[object] = [RuntimeError("rate limit")] * 7 + [
        filled_order_response,
    ]
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(side_effect=side_effects)
    monitor = OrderMonitor(exchange=exchange, timeout_s=1000)

    result = await monitor._poll_status("BTCUSDT", 123)

    assert result is filled_order_response
    # Delays after each of the 7 failures: 2,4,8,16,30,30,30
    assert sleep_calls == [2, 4, 8, 16, 30, 30, 30]


@pytest.mark.asyncio
async def test_monitor_backoff_resets_on_successful_non_terminal(
    filled_order_response,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a successful non-terminal poll, the backoff returns to 1s."""
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(monitor_module.asyncio, "sleep", fake_sleep)

    # NEW -> NEW means the monitor keeps polling; healthy polls stay at 1s.
    new_order = filled_order_response.model_copy(update={"status": OrderStatus.NEW})
    side_effects = [
        RuntimeError("rate limit"),  # failure_count -> 1, sleep 2
        RuntimeError("rate limit"),  # failure_count -> 2, sleep 4
        new_order,  # success, reset -> sleep 1
        filled_order_response,  # terminal, returns
    ]
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(side_effect=side_effects)
    monitor = OrderMonitor(exchange=exchange, timeout_s=1000)

    result = await monitor._poll_status("BTCUSDT", 123)

    assert result is filled_order_response
    assert sleep_calls == [2, 4, 1]
