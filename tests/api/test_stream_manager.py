import asyncio
from collections.abc import AsyncIterator
from typing import Any, Self
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from kavzi_trader.api.binance.websocket.stream_manager import StreamManager
from kavzi_trader.api.common.exceptions import APIError

_MODULE = "kavzi_trader.api.binance.websocket.stream_manager"


class _IdleSocket:
    """Socket stand-in whose recv blocks until the task is cancelled."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def recv(self) -> dict[str, Any]:
        await asyncio.Event().wait()
        return {}


async def _noop_callback(msg: dict[str, Any]) -> None:
    return None


@pytest_asyncio.fixture
async def mock_client() -> AsyncIterator[AsyncMock]:
    client = AsyncMock()
    with (
        patch(f"{_MODULE}.AsyncClient.create", new_callable=AsyncMock) as create,
        patch(f"{_MODULE}.BinanceSocketManager"),
    ):
        create.return_value = client
        yield client


@pytest.mark.asyncio
async def test_concurrent_start_creates_single_client() -> None:
    async def slow_create(**_: object) -> AsyncMock:
        await asyncio.sleep(0.01)
        return AsyncMock()

    with (
        patch(f"{_MODULE}.AsyncClient.create", side_effect=slow_create) as create,
        patch(f"{_MODULE}.BinanceSocketManager"),
    ):
        manager = StreamManager()
        await asyncio.gather(*(manager.start() for _ in range(5)))

    assert create.call_count == 1
    assert manager.is_connected()


@pytest.mark.asyncio
async def test_stop_resets_state_when_close_raises(mock_client: AsyncMock) -> None:
    mock_client.close_connection.side_effect = RuntimeError("boom")
    manager = StreamManager()
    await manager.start()
    manager.register_stream("a@trade", _IdleSocket(), _noop_callback)  # type: ignore[arg-type]

    with pytest.raises(APIError):
        await manager.stop()

    assert not manager.is_connected()
    assert manager.list_active_streams() == []
    assert manager.stream_callbacks == {}
    with pytest.raises(RuntimeError):
        _ = manager.bsm


@pytest.mark.asyncio
async def test_manager_can_restart_after_failed_stop(mock_client: AsyncMock) -> None:
    mock_client.close_connection.side_effect = RuntimeError("boom")
    manager = StreamManager()
    await manager.start()
    with pytest.raises(APIError):
        await manager.stop()

    await manager.start()

    assert manager.is_connected()


@pytest.mark.asyncio
async def test_unregister_removes_callback() -> None:
    manager = StreamManager()
    manager.add_stream_callback("a@trade", _noop_callback)
    manager.register_stream("a@trade", _IdleSocket(), _noop_callback)  # type: ignore[arg-type]

    await manager.unregister_stream("a@trade")

    assert manager.stream_callbacks == {}


@pytest.mark.asyncio
async def test_unregister_removes_callbacks_added_but_never_registered() -> None:
    manager = StreamManager()
    manager.add_stream_callback("a@trade", _noop_callback)

    await manager.unregister_stream("a@trade")

    assert manager.stream_callbacks == {}


@pytest.mark.asyncio
async def test_unregister_multiplex_removes_component_callbacks() -> None:
    manager = StreamManager()
    manager.add_stream_callback("a@trade", _noop_callback)
    manager.add_stream_callback("b@trade", _noop_callback)
    manager.add_stream_callback("other@trade", _noop_callback)
    manager.register_stream("a@trade/b@trade", _IdleSocket(), _noop_callback)  # type: ignore[arg-type]

    await manager.unregister_stream("a@trade/b@trade")

    assert set(manager.stream_callbacks) == {"other@trade"}
