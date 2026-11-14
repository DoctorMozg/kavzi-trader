import asyncio
import functools
import itertools
import signal
from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.orchestrator import orchestrator as orchestrator_module
from kavzi_trader.orchestrator.config import OrchestratorConfigSchema
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.orchestrator.loops.ingest import DataIngestLoop
from kavzi_trader.orchestrator.loops.order_flow import OrderFlowLoop
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.orchestrator.loops.reasoning import ReasoningLoop
from kavzi_trader.orchestrator.orchestrator import (
    LoopRestartLimitError,
    TradingOrchestrator,
)

TEST_TIMEOUT_S = 3

LoopBody = Callable[[], Awaitable[None]]


class _Loop:
    """Stands in for any loop class; `run` executes the scripted body."""

    def __init__(self, body: LoopBody | None = None) -> None:
        self._body = body
        self.runs = 0

    async def warm_up(self) -> None:
        return None

    async def run(self) -> None:
        self.runs += 1
        if self._body is None:
            await asyncio.Event().wait()
        else:
            await self._body()


def _config(**overrides: float) -> OrchestratorConfigSchema:
    values: dict[str, float] = {
        "loop_restart_base_delay_s": 0.0,
        "loop_restart_max_delay_s": 0.0,
        "graceful_shutdown_timeout_s": 1,
    }
    values.update(overrides)
    return OrchestratorConfigSchema.model_validate(values)


def _orchestrator(
    ingest: _Loop,
    config: OrchestratorConfigSchema | None = None,
    state_manager: AsyncMock | None = None,
    shutdown_hooks: dict[str, Callable[[], Awaitable[None]]] | None = None,
) -> TradingOrchestrator:
    return TradingOrchestrator(
        config=config or _config(),
        state_manager=state_manager or AsyncMock(),
        ingest_loop=cast("DataIngestLoop", ingest),
        order_flow_loop=cast("OrderFlowLoop", _Loop()),
        reasoning_loop=cast("ReasoningLoop", _Loop()),
        execution_loop=cast("ExecutionLoop", _Loop()),
        position_loop=cast("PositionManagementLoop", _Loop()),
        shutdown_hooks=shutdown_hooks,
    )


async def _wait_until(predicate: Callable[[], bool]) -> None:
    while not predicate():
        await asyncio.sleep(0.005)


class TestSupervisor:
    async def test_crashed_loop_restarts_with_capped_exponential_backoff(self) -> None:
        loop_time = asyncio.get_running_loop().time
        starts: list[float] = []

        async def crash() -> None:
            starts.append(loop_time())
            msg = "boom"
            raise RuntimeError(msg)

        orchestrator = _orchestrator(
            _Loop(crash),
            _config(
                loop_restart_base_delay_s=0.02,
                loop_restart_max_delay_s=0.08,
                loop_max_crashes=100,
            ),
        )

        async with asyncio.timeout(TEST_TIMEOUT_S):
            runner = asyncio.create_task(orchestrator.start())
            await _wait_until(lambda: len(starts) >= 5)
            orchestrator.request_shutdown()
            await runner

        gaps = [b - a for a, b in itertools.pairwise(starts)]
        # Delay doubles from the base and stops growing at the cap.
        assert gaps[0] >= 0.02
        assert gaps[1] >= 0.04
        assert gaps[2] >= 0.08
        assert gaps[3] >= 0.08

    async def test_repeated_crashes_escalate_to_shutdown(self) -> None:
        async def crash() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        hook = AsyncMock()
        state_manager = AsyncMock()
        ingest = _Loop(crash)
        orchestrator = _orchestrator(
            ingest,
            _config(loop_max_crashes=3),
            state_manager,
            {"ws": hook},
        )

        async with asyncio.timeout(TEST_TIMEOUT_S):
            with pytest.raises(LoopRestartLimitError, match="ingest"):
                await orchestrator.start()

        assert ingest.runs == 3
        hook.assert_awaited_once()
        state_manager.close.assert_awaited_once()

    async def test_crashes_outside_the_window_do_not_escalate(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ticks = iter(range(0, 10_000, 60))
        monkeypatch.setattr(orchestrator_module, "_monotonic_s", lambda: next(ticks))

        async def crash() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        ingest = _Loop(crash)
        orchestrator = _orchestrator(
            ingest,
            _config(loop_max_crashes=3, loop_crash_window_s=100),
        )

        async with asyncio.timeout(TEST_TIMEOUT_S):
            runner = asyncio.create_task(orchestrator.start())
            await _wait_until(lambda: ingest.runs >= 6)
            assert not runner.done()
            orchestrator.request_shutdown()
            await runner

    async def test_unexpectedly_cancelled_loop_is_restarted(self) -> None:
        async def cancel_once() -> None:
            if ingest.runs == 1:
                task = asyncio.current_task()
                assert task is not None
                task.cancel()
            await asyncio.Event().wait()

        ingest = _Loop(cancel_once)
        orchestrator = _orchestrator(ingest)

        async with asyncio.timeout(TEST_TIMEOUT_S):
            runner = asyncio.create_task(orchestrator.start())
            await _wait_until(lambda: ingest.runs >= 2)
            orchestrator.request_shutdown()
            await runner

        assert ingest.runs >= 2

    async def test_loops_are_not_restarted_during_shutdown(self) -> None:
        ingest = _Loop()
        orchestrator = _orchestrator(ingest)

        async with asyncio.timeout(TEST_TIMEOUT_S):
            runner = asyncio.create_task(orchestrator.start())
            await _wait_until(lambda: ingest.runs == 1)
            orchestrator.request_shutdown()
            await runner

        assert ingest.runs == 1


class TestShutdown:
    async def test_closes_loops_then_resources_in_order(self) -> None:
        order: list[str] = []

        async def body() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                order.append("loops")

        def closer(name: str) -> Callable[[], Awaitable[None]]:
            async def close() -> None:
                order.append(name)

            return close

        state_manager = AsyncMock()
        state_manager.close.side_effect = closer("state")
        ingest = _Loop(body)
        orchestrator = _orchestrator(
            ingest,
            state_manager=state_manager,
            shutdown_hooks={
                "websocket": closer("websocket"),
                "exchange": closer("exchange"),
                "redis": closer("redis"),
            },
        )

        async with asyncio.timeout(TEST_TIMEOUT_S):
            runner = asyncio.create_task(orchestrator.start())
            await _wait_until(lambda: ingest.runs == 1)
            orchestrator.request_shutdown()
            await runner

        assert order == ["loops", "websocket", "exchange", "redis", "state"]

    async def test_runs_when_start_is_cancelled(self) -> None:
        hook = AsyncMock()
        state_manager = AsyncMock()
        ingest = _Loop()
        orchestrator = _orchestrator(
            ingest,
            state_manager=state_manager,
            shutdown_hooks={"ws": hook},
        )

        async with asyncio.timeout(TEST_TIMEOUT_S):
            runner = asyncio.create_task(orchestrator.start())
            await _wait_until(lambda: ingest.runs == 1)
            runner.cancel()
            with pytest.raises(asyncio.CancelledError):
                await runner

        hook.assert_awaited_once()
        state_manager.close.assert_awaited_once()

    async def test_runs_when_startup_fails(self) -> None:
        state_manager = AsyncMock()
        state_manager.reconcile_with_exchange.side_effect = RuntimeError("redis down")
        hook = AsyncMock()
        orchestrator = _orchestrator(
            _Loop(),
            state_manager=state_manager,
            shutdown_hooks={"ws": hook},
        )

        async with asyncio.timeout(TEST_TIMEOUT_S):
            with pytest.raises(RuntimeError, match="redis down"):
                await orchestrator.start()

        hook.assert_awaited_once()
        state_manager.close.assert_awaited_once()

    async def test_is_idempotent(self) -> None:
        hook = AsyncMock()
        state_manager = AsyncMock()
        orchestrator = _orchestrator(
            _Loop(),
            state_manager=state_manager,
            shutdown_hooks={"ws": hook},
        )

        async with asyncio.timeout(TEST_TIMEOUT_S):
            await orchestrator.shutdown()
            await orchestrator.shutdown()

        hook.assert_awaited_once()
        state_manager.close.assert_awaited_once()

    async def test_failing_hook_does_not_skip_later_resources(self) -> None:
        failing = AsyncMock(side_effect=RuntimeError("close failed"))
        later = AsyncMock()
        state_manager = AsyncMock()
        orchestrator = _orchestrator(
            _Loop(),
            state_manager=state_manager,
            shutdown_hooks={"ws": failing, "redis": later},
        )

        async with asyncio.timeout(TEST_TIMEOUT_S):
            await orchestrator.shutdown()

        later.assert_awaited_once()
        state_manager.close.assert_awaited_once()

    async def test_loop_ignoring_cancellation_is_abandoned_after_timeout(self) -> None:
        async def stubborn() -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(0.5)

        hook = AsyncMock()
        ingest = _Loop(stubborn)
        orchestrator = _orchestrator(
            ingest,
            _config(graceful_shutdown_timeout_s=0.05),
            shutdown_hooks={"ws": hook},
        )
        loop_time = asyncio.get_running_loop().time

        async with asyncio.timeout(TEST_TIMEOUT_S):
            runner = asyncio.create_task(orchestrator.start())
            await _wait_until(lambda: ingest.runs == 1)
            requested_at = loop_time()
            orchestrator.request_shutdown()
            await runner

        assert loop_time() - requested_at < 0.4
        hook.assert_awaited_once()

    async def test_signals_request_shutdown_and_are_released(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        loop = asyncio.get_running_loop()
        added: dict[int, Callable[[], None]] = {}
        removed: list[int] = []
        monkeypatch.setattr(
            loop,
            "add_signal_handler",
            lambda sig, callback, *args: added.__setitem__(
                sig,
                functools.partial(callback, *args),
            ),
        )

        def remove(sig: int) -> bool:
            removed.append(sig)
            return True

        monkeypatch.setattr(loop, "remove_signal_handler", remove)
        ingest = _Loop()
        orchestrator = _orchestrator(ingest)

        async with asyncio.timeout(TEST_TIMEOUT_S):
            runner = asyncio.create_task(orchestrator.start())
            await _wait_until(lambda: ingest.runs == 1)
            assert set(added) == {signal.SIGINT, signal.SIGTERM}
            added[signal.SIGTERM]()
            await runner

        assert set(removed) == {signal.SIGINT, signal.SIGTERM}
