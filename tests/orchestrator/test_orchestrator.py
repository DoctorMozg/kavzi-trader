import asyncio
from datetime import UTC, datetime
from decimal import Decimal
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
from kavzi_trader.spine.state.schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)


class DummyLoop:
    async def run(self) -> None:
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_orchestrator_start_runs_loops() -> None:
    config = OrchestratorConfigSchema(health_check_interval_s=1)
    state_manager = AsyncMock()
    health = HealthChecker()
    orchestrator = TradingOrchestrator(
        config=config,
        state_manager=state_manager,
        ingest_loop=cast("DataIngestLoop", DummyLoop()),
        order_flow_loop=cast("OrderFlowLoop", DummyLoop()),
        reasoning_loop=cast("ReasoningLoop", DummyLoop()),
        execution_loop=cast("ExecutionLoop", DummyLoop()),
        position_loop=cast("PositionManagementLoop", DummyLoop()),
        health_checker=health,
    )

    task = asyncio.create_task(orchestrator.start())
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    state_manager.connect.assert_called_once()
    state_manager.reconcile_with_exchange.assert_called_once()


class FakePriceProvider:
    def __init__(self, prices: dict[str, Decimal]) -> None:
        self._prices = prices

    def get_current_price(self, symbol: str) -> Decimal:
        return self._prices.get(symbol, Decimal(0))


def test_build_position_snapshots_computes_pnl() -> None:
    now = datetime.now(UTC)
    price_provider = FakePriceProvider({"DOGEUSDT": Decimal("0.09008")})
    orchestrator = TradingOrchestrator(
        config=OrchestratorConfigSchema(),
        state_manager=AsyncMock(),
        ingest_loop=cast("DataIngestLoop", DummyLoop()),
        order_flow_loop=cast("OrderFlowLoop", DummyLoop()),
        reasoning_loop=cast("ReasoningLoop", DummyLoop()),
        execution_loop=cast("ExecutionLoop", DummyLoop()),
        position_loop=cast("PositionManagementLoop", DummyLoop()),
        health_checker=HealthChecker(),
        price_provider=price_provider,
    )
    positions = [
        PositionSchema(
            id="pos-1",
            symbol="DOGEUSDT",
            side="SHORT",
            quantity=Decimal(86207),
            entry_price=Decimal("0.09055"),
            stop_loss=Decimal("0.09112"),
            take_profit=Decimal("0.08942"),
            current_stop_loss=Decimal("0.09112"),
            management_config=PositionManagementConfigSchema(),
            leverage=3,
            opened_at=now,
            updated_at=now,
        ),
    ]
    snapshots = orchestrator._build_position_snapshots(positions)

    assert len(snapshots) == 1
    pnl = snapshots[0].unrealized_pnl
    # SHORT: (entry - current) * qty = (0.09055 - 0.09008) * 86207 = ~40.52
    assert pnl > Decimal(0)
    expected = (Decimal("0.09055") - Decimal("0.09008")) * Decimal(86207)
    assert pnl == expected


def test_build_position_snapshots_long_pnl() -> None:
    now = datetime.now(UTC)
    price_provider = FakePriceProvider({"BTCUSDT": Decimal(51000)})
    orchestrator = TradingOrchestrator(
        config=OrchestratorConfigSchema(),
        state_manager=AsyncMock(),
        ingest_loop=cast("DataIngestLoop", DummyLoop()),
        order_flow_loop=cast("OrderFlowLoop", DummyLoop()),
        reasoning_loop=cast("ReasoningLoop", DummyLoop()),
        execution_loop=cast("ExecutionLoop", DummyLoop()),
        position_loop=cast("PositionManagementLoop", DummyLoop()),
        health_checker=HealthChecker(),
        price_provider=price_provider,
    )
    positions = [
        PositionSchema(
            id="pos-2",
            symbol="BTCUSDT",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal(50000),
            stop_loss=Decimal(49000),
            take_profit=Decimal(52000),
            current_stop_loss=Decimal(49000),
            management_config=PositionManagementConfigSchema(),
            leverage=3,
            opened_at=now,
            updated_at=now,
        ),
    ]
    snapshots = orchestrator._build_position_snapshots(positions)

    assert len(snapshots) == 1
    pnl = snapshots[0].unrealized_pnl
    # LONG: (current - entry) * qty = (51000 - 50000) * 0.1 = 100
    assert pnl == Decimal(100)
