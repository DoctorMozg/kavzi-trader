from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kavzi_trader.api.common.models import (
    OrderResponseSchema,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


@pytest.fixture()
def execution_config() -> ExecutionConfigSchema:
    return ExecutionConfigSchema()


@pytest.fixture()
def decision_message() -> DecisionMessageSchema:
    return DecisionMessageSchema(
        decision_id="decision-1",
        symbol="BTCUSDT",
        action="BUY",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        quantity=Decimal("1"),
        raw_confidence=0.8,
        calibrated_confidence=0.7,
        volatility_regime=VolatilityRegime.NORMAL,
        position_management=PositionManagementConfigSchema(),
        created_at_ms=1_000,
        expires_at_ms=60_000,
        current_atr=Decimal("2"),
        atr_history=[Decimal("1.8"), Decimal("2.1")],
    )


@pytest.fixture()
def filled_order_response() -> OrderResponseSchema:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return OrderResponseSchema(
        symbol="BTCUSDT",
        order_id=123,
        client_order_id="decision-1",
        transact_time=now,
        price=Decimal("100"),
        orig_qty=Decimal("1"),
        executed_qty=Decimal("1"),
        status=OrderStatus.FILLED,
        time_in_force=TimeInForce.GTC,
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        time=now,
    )
