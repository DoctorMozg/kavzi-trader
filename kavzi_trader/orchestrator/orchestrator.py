from __future__ import annotations

import asyncio
import logging

from kavzi_trader.orchestrator.config import OrchestratorConfigSchema
from kavzi_trader.orchestrator.health import HealthChecker
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.orchestrator.loops.ingest import DataIngestLoop
from kavzi_trader.orchestrator.loops.order_flow import OrderFlowLoop
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.orchestrator.loops.reasoning import ReasoningLoop
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


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
        health_checker: HealthChecker,
        report_populator: TradeReportPopulator | None = None,
    ) -> None:
        self._config = config
        self._state_manager = state_manager
        self._ingest_loop = ingest_loop
        self._order_flow_loop = order_flow_loop
        self._reasoning_loop = reasoning_loop
        self._execution_loop = execution_loop
        self._position_loop = position_loop
        self._health_checker = health_checker
        self._report_populator = report_populator
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        logger.info("Orchestrator starting — connecting to state store")
        await self._state_manager.connect()
        logger.info("State store connected, beginning reconciliation")
        await self._state_manager.reconcile_with_exchange()
        logger.info("Reconciliation complete, launching async loops")
        self._tasks = [
            asyncio.create_task(self._ingest_loop.run()),
            asyncio.create_task(self._order_flow_loop.run()),
            asyncio.create_task(self._reasoning_loop.run()),
            asyncio.create_task(self._execution_loop.run()),
            asyncio.create_task(self._position_loop.run()),
            asyncio.create_task(self._health_loop()),
        ]
        if self._report_populator is not None:
            self._tasks.append(
                asyncio.create_task(self._report_loop()),
            )
        logger.info(
            "All %d loops launched, orchestrator running", len(self._tasks),
        )
        await asyncio.gather(*self._tasks)

    async def shutdown(self) -> None:
        logger.info("Orchestrator shutting down — cancelling %d tasks", len(self._tasks))
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._state_manager.close()
        logger.info("Orchestrator shutdown complete")

    async def _health_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._config.health_check_interval_s)
                if not self._health_checker.is_healthy():
                    logger.warning("Health check failed")
            except Exception:
                logger.exception("Health check loop encountered an error")

    async def _report_loop(self) -> None:
        """Periodically refreshes balance data in the report."""
        while True:
            try:
                await asyncio.sleep(5)
                if self._report_populator is None:
                    continue
                account = await self._state_manager.get_account_state()
                positions = await self._state_manager.get_all_positions()
                if account is not None:
                    await self._report_populator.update_balance(
                        current_balance_usdt=account.total_balance_usdt,
                        unrealized_pnl_usdt=account.unrealized_pnl,
                        active_positions_count=len(positions),
                    )
            except Exception:
                logger.exception(
                    "Report loop encountered an error, continuing",
                )
