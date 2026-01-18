import asyncio
from typing import cast
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.orchestrator.config import OrchestratorConfigSchema
from kavzi_trader.orchestrator.health import HealthChecker
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.orchestrator.loops.ingest import DataIngestLoop
from kavzi_trader.orchestrator.loops.order_flow import OrderFlowLoop
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.orchestrator.loops.reasoning import ReasoningLoop
from kavzi_trader.orchestrator.orchestrator import TradingOrchestrator


class DummyLoop:
    async def run(self) -> None:
        await asyncio.sleep(0)


@pytest.mark.asyncio()
async def test_orchestrator_start_runs_loops() -> None:
    config = OrchestratorConfigSchema(health_check_interval_s=1)
    state_manager = AsyncMock()
    health = HealthChecker()
    orchestrator = TradingOrchestrator(
        config=config,
        state_manager=state_manager,
        ingest_loop=cast(DataIngestLoop, DummyLoop()),
        order_flow_loop=cast(OrderFlowLoop, DummyLoop()),
        reasoning_loop=cast(ReasoningLoop, DummyLoop()),
        execution_loop=cast(ExecutionLoop, DummyLoop()),
        position_loop=cast(PositionManagementLoop, DummyLoop()),
        health_checker=health,
    )

    task = asyncio.create_task(orchestrator.start())
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    state_manager.connect.assert_called_once()
    state_manager.reconcile_with_exchange.assert_called_once()
