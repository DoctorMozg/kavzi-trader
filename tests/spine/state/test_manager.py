from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kavzi_trader.spine.state.config import RedisConfigSchema
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    OpenOrderSchema,
    PositionSchema,
)


class TestStateManager:
    @pytest.fixture
    def mock_exchange(self) -> AsyncMock:
        exchange = AsyncMock()
        exchange.get_ticker = AsyncMock(
            return_value=MagicMock(last_price=Decimal(50000)),
        )
        return exchange

    @pytest.fixture
    def manager(
        self,
        redis_config: RedisConfigSchema,
        mock_exchange: AsyncMock,
    ) -> StateManager:
        with patch(
            "kavzi_trader.spine.state.manager.RedisStateClient",
        ) as mock_redis_cls:
            mock_redis = AsyncMock()
            mock_redis_cls.return_value = mock_redis
            manager = StateManager(redis_config, mock_exchange)
            manager._redis_client = mock_redis
            return manager

    async def test_connect(self, manager: StateManager):
        await manager.connect()
        manager._redis_client.connect.assert_called_once()

    async def test_close(self, manager: StateManager):
        await manager.close()
        manager._redis_client.close.assert_called_once()

    async def test_get_position(
        self,
        manager: StateManager,
        sample_position: PositionSchema,
    ):
        manager._position_store.get_by_symbol = AsyncMock(return_value=sample_position)

        result = await manager.get_position("BTCUSDT")

        assert result == sample_position

    async def test_get_all_positions(
        self,
        manager: StateManager,
        sample_position: PositionSchema,
    ):
        manager._position_store.get_all = AsyncMock(return_value=[sample_position])

        result = await manager.get_all_positions()

        assert len(result) == 1

    async def test_update_position(
        self,
        manager: StateManager,
        sample_position: PositionSchema,
    ):
        manager._position_store.save = AsyncMock()

        await manager.update_position(sample_position)

        manager._position_store.save.assert_called_once_with(sample_position)

    async def test_remove_position(self, manager: StateManager):
        manager._position_store.delete = AsyncMock()

        await manager.remove_position("pos_123")

        manager._position_store.delete.assert_called_once_with("pos_123")

    async def test_get_open_orders_all(
        self,
        manager: StateManager,
        sample_order: OpenOrderSchema,
    ):
        manager._order_store.get_all = AsyncMock(return_value=[sample_order])

        result = await manager.get_open_orders()

        assert len(result) == 1

    async def test_get_open_orders_by_symbol(
        self,
        manager: StateManager,
        sample_order: OpenOrderSchema,
    ):
        manager._order_store.get_by_symbol = AsyncMock(return_value=[sample_order])

        result = await manager.get_open_orders("BTCUSDT")

        manager._order_store.get_by_symbol.assert_called_once_with("BTCUSDT")
        assert len(result) == 1

    async def test_save_order(
        self,
        manager: StateManager,
        sample_order: OpenOrderSchema,
    ):
        manager._order_store.save = AsyncMock()

        await manager.save_order(sample_order)

        manager._order_store.save.assert_called_once_with(sample_order)

    async def test_remove_order(self, manager: StateManager):
        manager._order_store.delete = AsyncMock()

        await manager.remove_order("order_789")

        manager._order_store.delete.assert_called_once_with("order_789")

    async def test_get_account_state(
        self,
        manager: StateManager,
        sample_account_state: AccountStateSchema,
    ):
        manager._account_store.get = AsyncMock(return_value=sample_account_state)

        result = await manager.get_account_state()

        assert result == sample_account_state

    async def test_get_current_drawdown(self, manager: StateManager):
        manager._account_store.get_drawdown = AsyncMock(return_value=Decimal("5.0"))

        result = await manager.get_current_drawdown()

        assert result == Decimal("5.0")

    async def test_get_current_price(
        self,
        manager: StateManager,
        mock_exchange: AsyncMock,
    ):
        result = await manager.get_current_price("BTCUSDT")

        assert result == Decimal(50000)
        mock_exchange.get_ticker.assert_called_once_with("BTCUSDT")

    async def test_properties(self, manager: StateManager):
        assert manager.positions == manager._position_store
        assert manager.orders == manager._order_store
        assert manager.account == manager._account_store

    async def test_reset_for_paper(self, manager: StateManager):
        manager._position_store.clear_all = AsyncMock(return_value=2)
        manager._order_store.clear_all = AsyncMock(return_value=3)
        manager._account_store.save = AsyncMock()

        await manager.reset_for_paper(Decimal(5000))

        manager._position_store.clear_all.assert_called_once()
        manager._order_store.clear_all.assert_called_once()
        manager._account_store.save.assert_called_once()
        saved_account = manager._account_store.save.call_args[0][0]
        assert saved_account.total_balance_usdt == Decimal(5000)
        assert saved_account.available_balance_usdt == Decimal(5000)
        assert saved_account.locked_balance_usdt == Decimal(0)
        assert saved_account.peak_balance == Decimal(5000)
        assert saved_account.current_drawdown_percent == Decimal(0)
