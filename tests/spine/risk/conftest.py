from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)


@pytest.fixture()
def risk_config() -> RiskConfigSchema:
    return RiskConfigSchema()


@pytest.fixture()
def atr_history_normal() -> list[Decimal]:
    return [Decimal(str(i)) for i in [100, 102, 98, 101, 99, 100, 103, 97, 100, 101]]


@pytest.fixture()
def mock_state_manager() -> MagicMock:
    manager = MagicMock()
    manager.get_current_drawdown = AsyncMock(return_value=Decimal("0"))
    manager.get_all_positions = AsyncMock(return_value=[])
    manager.get_account_state = AsyncMock(
        return_value=AccountStateSchema(
            total_balance_usdt=Decimal("10000"),
            available_balance_usdt=Decimal("10000"),
            locked_balance_usdt=Decimal("0"),
            peak_balance=Decimal("10000"),
            updated_at=datetime.now(UTC),
        ),
    )
    return manager


@pytest.fixture()
def sample_position() -> PositionSchema:
    return PositionSchema(
        id="pos-1",
        symbol="BTCUSDT",
        side="LONG",
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("52000"),
        current_stop_loss=Decimal("49000"),
        management_config=PositionManagementConfigSchema(),
        opened_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
