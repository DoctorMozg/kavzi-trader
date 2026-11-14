from __future__ import annotations

import asyncio
import logging
import signal
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from kavzi_trader.external.loop import ExternalSentimentLoop
from kavzi_trader.orchestrator.config import OrchestratorConfigSchema
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.orchestrator.loops.ingest import DataIngestLoop
from kavzi_trader.orchestrator.loops.order_flow import OrderFlowLoop
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.orchestrator.loops.reasoning import ReasoningLoop
from kavzi_trader.orchestrator.loops.ui_snapshot import UiSnapshotLoop
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)

LoopFactory = Callable[[], Coroutine[Any, Any, None]]
CloseCallback = Callable[[], Awaitable[None]]

_SHUTDOWN_SIGNALS = (signal.SIGINT, signal.SIGTERM)


def _monotonic_s() -> float:
    return time.monotonic()


class LoopRestartLimitError(RuntimeError):
    """A supervised loop kept dying; the orchestrator gave up on it."""


class TradingOrchestrator:
    """Runs the data ingest, reasoning, execution, and position loops."""

    def __init__(
        self,
        config: OrchestratorConfigSchema,
        state_manager: StateManager,
        ingest_loop: DataIngestLoop,
        order_flow_loop: OrderFlowLoop,
        reasoning_loop: ReasoningLoop,
        execution_loop: ExecutionLoop,
        position_loop: PositionManagementLoop,
        ui_snapshot_loop: UiSnapshotLoop | None = None,
        is_paper: bool = False,
        external_sentiment_loop: ExternalSentimentLoop | None = None,
        shutdown_hooks: dict[str, CloseCallback] | None = None,
    ) -> None:
        self._config = config
        self._state_manager = state_manager
        self._ingest_loop = ingest_loop
        self._order_flow_loop = order_flow_loop
        self._reasoning_loop = reasoning_loop
        self._execution_loop = execution_loop
        self._position_loop = position_loop
        self._ui_snapshot_loop = ui_snapshot_loop
        self._is_paper = is_paper
        self._external_sentiment_loop = external_sentiment_loop
        self._tasks: set[asyncio.Task[None]] = set()
        self._loop_factories: dict[str, LoopFactory] = {}
        # Insertion order is the close order; the state manager always closes last.
        self._shutdown_hooks = shutdown_hooks or {}
        self._stop_event = asyncio.Event()
        self._shutdown_started = False
        self._crash_times_s: defaultdict[str, deque[float]] = defaultdict(deque)
        self._escalation: LoopRestartLimitError | None = None

    async def start(self) -> None:
        self._install_signal_handlers()
        try:
            await self._launch()
            await self._supervise_tasks()
        finally:
            self._remove_signal_handlers()
            await self.shutdown()
        if self._escalation is not None:
            raise self._escalation

    def running_loop_names(self) -> list[str]:
        return sorted(task.get_name() for task in self._tasks if not task.done())

    def request_shutdown(self) -> None:
        """Ask the supervisor to stop; safe to call from a signal handler."""
        if not self._stop_event.is_set():
            logger.warning("Orchestrator shutdown requested")
        self._stop_event.set()

    async def _launch(self) -> None:
        logger.info("Orchestrator starting — connecting to state store")
        await self._state_manager.connect()
        if self._is_paper:
            logger.info(
                "Paper mode: skipping exchange reconciliation",
            )
        else:
            logger.info("State store connected, beginning reconciliation")
            await self._state_manager.reconcile_with_exchange()
            logger.info("Reconciliation complete")
        if self._external_sentiment_loop is not None:
            await self._external_sentiment_loop.warm_up()
        logger.info("Warming up order flow data")
        await self._order_flow_loop.warm_up()
        logger.info("Launching async loops")
        self._loop_factories = {
            "ingest": self._ingest_loop.run,
            "order_flow": self._order_flow_loop.run,
            "reasoning": self._reasoning_loop.run,
            "execution": self._execution_loop.run,
            "position": self._position_loop.run,
        }
        if self._ui_snapshot_loop is not None:
            ui_loop = self._ui_snapshot_loop
            self._loop_factories["ui_snapshot"] = lambda: ui_loop.run(
                self.running_loop_names,
            )
        if self._external_sentiment_loop is not None:
            self._loop_factories["external_sentiment"] = (
                self._external_sentiment_loop.run
            )
        for name, factory in self._loop_factories.items():
            self._spawn(name, factory, delay_s=0.0)
        logger.info(
            "All %d loops launched, orchestrator running",
            len(self._tasks),
        )

    def _spawn(self, name: str, factory: LoopFactory, delay_s: float) -> None:
        task = asyncio.create_task(self._run_after_delay(factory, delay_s), name=name)
        self._tasks.add(task)

    @staticmethod
    async def _run_after_delay(factory: LoopFactory, delay_s: float) -> None:
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        await factory()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in _SHUTDOWN_SIGNALS:
            loop.add_signal_handler(sig, self._on_signal, sig)

    def _remove_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in _SHUTDOWN_SIGNALS:
            loop.remove_signal_handler(sig)

    def _on_signal(self, sig: signal.Signals) -> None:
        logger.warning("Received %s, shutting down", sig.name)
        self.request_shutdown()

    async def _supervise_tasks(self) -> None:
        """Restart loops that die unexpectedly; give up when one keeps dying."""
        stop_waiter = asyncio.create_task(self._wait_for_stop(), name="stop_waiter")
        try:
            while not self._stop_event.is_set():
                done, _ = await asyncio.wait(
                    {*self._tasks, stop_waiter},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done - {stop_waiter}:
                    self._tasks.discard(task)
                    if not self._handle_terminated(task):
                        return
        finally:
            stop_waiter.cancel()

    async def _wait_for_stop(self) -> None:
        await self._stop_event.wait()

    def _handle_terminated(self, task: asyncio.Task[None]) -> bool:
        """Schedule a restart; return False once the orchestrator must stop."""
        name = task.get_name()
        if self._stop_event.is_set():
            return True
        if task.cancelled():
            logger.warning("Task %s was cancelled unexpectedly, restarting", name)
        elif (exc := task.exception()) is not None:
            logger.error("Task %s crashed, restarting", name, exc_info=exc)
        else:
            logger.warning(
                "Task %s exited cleanly (unexpected), restarting",
                name,
            )
        crashes = self._record_crash(name)
        if crashes >= self._config.loop_max_crashes:
            msg = (
                f"Loop {name} terminated {crashes} times within "
                f"{self._config.loop_crash_window_s}s"
            )
            logger.critical(
                "%s; shutting down orchestrator",
                msg,
                extra={"loop": name, "crashes": crashes},
            )
            self._escalation = LoopRestartLimitError(msg)
            self._stop_event.set()
            return False
        delay_s = min(
            self._config.loop_restart_base_delay_s * 2 ** (crashes - 1),
            self._config.loop_restart_max_delay_s,
        )
        self._spawn(name, self._loop_factories[name], delay_s)
        logger.info(
            "Task %s restart scheduled in %.1fs",
            name,
            delay_s,
            extra={"loop": name, "crashes": crashes, "delay_s": delay_s},
        )
        return True

    def _record_crash(self, name: str) -> int:
        now_s = _monotonic_s()
        recent = self._crash_times_s[name]
        recent.append(now_s)
        while recent[0] <= now_s - self._config.loop_crash_window_s:
            recent.popleft()
        return len(recent)

    async def shutdown(self) -> None:
        """Stop loops and close resources; exchange-side SL/TP keep protecting."""
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._stop_event.set()
        await self._stop_loops()
        for name, close in self._shutdown_hooks.items():
            await self._close_resource(name, close)
        await self._close_resource("state_manager", self._state_manager.close)
        logger.info("Orchestrator shutdown complete")

    async def _stop_loops(self) -> None:
        tasks = set(self._tasks)
        logger.info(
            "Orchestrator shutting down — cancelling %d tasks",
            len(tasks),
        )
        for task in tasks:
            task.cancel()
        if not tasks:
            return
        _, pending = await asyncio.wait(
            tasks,
            timeout=self._config.graceful_shutdown_timeout_s,
        )
        if pending:
            logger.error(
                "Tasks still running after %.1fs shutdown timeout: %s",
                self._config.graceful_shutdown_timeout_s,
                sorted(task.get_name() for task in pending),
            )

    async def _close_resource(self, name: str, close: CloseCallback) -> None:
        # Every resource gets its turn even when an earlier one fails or hangs.
        try:
            async with asyncio.timeout(self._config.graceful_shutdown_timeout_s):
                await close()
        except Exception:
            logger.exception("Failed to close %s during shutdown", name)
