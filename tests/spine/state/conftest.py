from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.models import OrderSide, OrderStatus, OrderType
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.state.config import RedisConfigSchema
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    OpenOrderSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)


@pytest.fixture()
def redis_config() -> RedisConfigSchema:
    return RedisConfigSchema(host="localhost", port=6379, db=0)


@pytest.fixture()
def mock_redis_client() -> AsyncMock:
    client = AsyncMock()
    client.hset = AsyncMock()
    client.hget = AsyncMock(return_value=None)
    client.hgetall = AsyncMock(return_value={})
    client.hdel = AsyncMock(return_value=1)
    client.delete = AsyncMock(return_value=1)
    client.keys = AsyncMock(return_value=[])
    client.set = AsyncMock()
    client.get = AsyncMock(return_value=None)
    return client


@pytest.fixture()
def sample_position() -> PositionSchema:
    now = utc_now()
    return PositionSchema(
        id="pos_123",
        symbol="BTCUSDT",
        side="LONG",
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000"),
        stop_loss=Decimal("48000"),
        take_profit=Decimal("55000"),
        current_stop_loss=Decimal("48000"),
        management_config=PositionManagementConfigSchema(),
        stop_loss_moved_to_breakeven=False,
        partial_exit_done=False,
        opened_at=now,
        updated_at=now,
    )


@pytest.fixture()
def sample_position_short() -> PositionSchema:
    now = utc_now()
    return PositionSchema(
        id="pos_456",
        symbol="ETHUSDT",
        side="SHORT",
        quantity=Decimal("1.0"),
        entry_price=Decimal("3000"),
        stop_loss=Decimal("3200"),
        take_profit=Decimal("2700"),
        current_stop_loss=Decimal("3200"),
        management_config=PositionManagementConfigSchema(),
        opened_at=now,
        updated_at=now,
    )


@pytest.fixture()
def sample_order() -> OpenOrderSchema:
    return OpenOrderSchema(
        order_id="order_789",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("49000"),
        quantity=Decimal("0.1"),
        executed_qty=Decimal("0"),
        status=OrderStatus.NEW,
        linked_position_id=None,
        created_at=utc_now(),
    )


@pytest.fixture()
def sample_sl_order() -> OpenOrderSchema:
    return OpenOrderSchema(
        order_id="order_sl_001",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.STOP_LOSS_LIMIT,
        price=Decimal("48000"),
        quantity=Decimal("0.1"),
        status=OrderStatus.NEW,
        linked_position_id="pos_123",
        created_at=utc_now(),
    )


@pytest.fixture()
def sample_tp_order() -> OpenOrderSchema:
    return OpenOrderSchema(
        order_id="order_tp_001",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.TAKE_PROFIT_LIMIT,
        price=Decimal("55000"),
        quantity=Decimal("0.1"),
        status=OrderStatus.NEW,
        linked_position_id="pos_123",
        created_at=utc_now(),
    )


@pytest.fixture()
def sample_account_state() -> AccountStateSchema:
    return AccountStateSchema(
        total_balance_usdt=Decimal("10000"),
        available_balance_usdt=Decimal("9000"),
        locked_balance_usdt=Decimal("1000"),
        unrealized_pnl=Decimal("50"),
        peak_balance=Decimal("10500"),
        current_drawdown_percent=Decimal("4.76"),
        updated_at=utc_now(),
    )
