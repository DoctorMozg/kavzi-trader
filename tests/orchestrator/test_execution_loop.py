import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


@pytest.mark.asyncio
async def test_execution_loop_dispatches() -> None:
    decision = DecisionMessageSchema(
        decision_id="decision-1",
        symbol="BTCUSDT",
        action="LONG",
        entry_price=Decimal(100),
        stop_loss=Decimal(95),
        take_profit=Decimal(110),
        quantity=Decimal(1),
        raw_confidence=0.8,
        calibrated_confidence=0.7,
        volatility_regime=VolatilityRegime.NORMAL,
        position_management=PositionManagementConfigSchema(),
        created_at_ms=1,
        expires_at_ms=60_000,
        current_atr=Decimal(2),
        atr_history=[],
    )
    redis_client = AsyncMock()
    redis_client.client.brpop = AsyncMock(
        side_effect=[("kt:decisions:pending", decision.model_dump_json()), None],
    )
    engine = AsyncMock()

    state_manager = AsyncMock()
    loop = ExecutionLoop(
        redis_client=redis_client,
        engine=engine,
        state_manager=state_manager,
    )
    task = asyncio.create_task(loop.run())
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    engine.execute.assert_called_once()
