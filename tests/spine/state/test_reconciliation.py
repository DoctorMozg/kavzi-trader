from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.models import (
    OrderResponseSchema,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.state.reconciliation import ReconciliationService
from kavzi_trader.spine.state.schemas import OpenOrderSchema, PositionSchema


class TestReconciliationService:
    @pytest.fixture
    def mock_exchange(self) -> AsyncMock:
        exchange = AsyncMock()
        exchange.get_account_info = AsyncMock(
            return_value={
                "balances": [
                    {"asset": "USDT", "free": "9000", "locked": "1000"},
                    {"asset": "BTC", "free": "0.1", "locked": "0"},
                ],
            },
        )
        exchange.get_open_orders = AsyncMock(return_value=[])
        return exchange

    @pytest.fixture
    def mock_position_store(self) -> AsyncMock:
        store = AsyncMock()
        store.get_all = AsyncMock(return_value=[])
        return store

    @pytest.fixture
    def mock_order_store(self) -> AsyncMock:
        store = AsyncMock()
        store.get_all = AsyncMock(return_value=[])
        store.get_by_position = AsyncMock(return_value=[])
        store.save = AsyncMock()
        store.delete = AsyncMock()
        return store

    @pytest.fixture
    def mock_account_store(self) -> AsyncMock:
        store = AsyncMock()
        store.update_balance = AsyncMock()
        return store

    @pytest.fixture
    def service(
        self,
        mock_exchange: AsyncMock,
        mock_position_store: AsyncMock,
        mock_order_store: AsyncMock,
        mock_account_store: AsyncMock,
    ) -> ReconciliationService:
        return ReconciliationService(
            exchange_client=mock_exchange,
            position_store=mock_position_store,
            order_store=mock_order_store,
            account_store=mock_account_store,
        )

    async def test_reconcile_success_empty_state(
        self,
        service: ReconciliationService,
        mock_account_store: AsyncMock,
    ):
        result = await service.reconcile()

        assert result.success is True
        assert len(result.discrepancies) == 0
        mock_account_store.update_balance.assert_called_once()

    async def test_reconcile_syncs_account_balance(
        self,
        service: ReconciliationService,
        mock_account_store: AsyncMock,
    ):
        await service.reconcile()

        mock_account_store.update_balance.assert_called_once_with(
            total_balance=Decimal(10000),
            available_balance=Decimal(9000),
            locked_balance=Decimal(1000),
        )

    async def test_reconcile_imports_unknown_orders(
        self,
        service: ReconciliationService,
        mock_exchange: AsyncMock,
        mock_order_store: AsyncMock,
    ):
        now = utc_now()
        exchange_order = OrderResponseSchema(
            symbol="BTCUSDT",
            order_id=12345,
            client_order_id="client_123",
            transact_time=now,
            price=Decimal(50000),
            orig_qty=Decimal("0.1"),
            executed_qty=Decimal(0),
            status=OrderStatus.NEW,
            time_in_force=TimeInForce.GTC,
            type=OrderType.LIMIT,
            side=OrderSide.BUY,
        )
        mock_exchange.get_open_orders.return_value = [exchange_order]

        result = await service.reconcile()

        assert result.success is True
        assert result.orders_synced == 1
        mock_order_store.save.assert_called_once()

    async def test_reconcile_removes_stale_orders(
        self,
        service: ReconciliationService,
        mock_order_store: AsyncMock,
    ):
        local_order = OpenOrderSchema(
            order_id="stale_order_999",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal(49000),
            quantity=Decimal("0.1"),
            status=OrderStatus.NEW,
            created_at=utc_now(),
        )
        mock_order_store.get_all.return_value = [local_order]

        result = await service.reconcile()

        assert result.success is True
        assert result.orders_removed == 1
        assert "Stale order" in result.discrepancies[0]
        mock_order_store.delete.assert_called_once_with("stale_order_999")

    async def test_reconcile_verifies_protective_orders(
        self,
        service: ReconciliationService,
        mock_position_store: AsyncMock,
        mock_order_store: AsyncMock,
        sample_position: PositionSchema,
        sample_sl_order: OpenOrderSchema,
        sample_tp_order: OpenOrderSchema,
    ):
        mock_position_store.get_all.return_value = [sample_position]
        mock_order_store.get_by_position.return_value = [
            sample_sl_order,
            sample_tp_order,
        ]

        result = await service.reconcile()

        assert result.success is True
        assert result.positions_synced == 1

    async def test_reconcile_reports_missing_sl(
        self,
        service: ReconciliationService,
        mock_position_store: AsyncMock,
        mock_order_store: AsyncMock,
        sample_position: PositionSchema,
        sample_tp_order: OpenOrderSchema,
    ):
        mock_position_store.get_all.return_value = [sample_position]
        mock_order_store.get_by_position.return_value = [sample_tp_order]

        result = await service.reconcile()

        assert result.success is True
        assert any("missing stop-loss" in d for d in result.discrepancies)

    async def test_reconcile_reports_missing_tp(
        self,
        service: ReconciliationService,
        mock_position_store: AsyncMock,
        mock_order_store: AsyncMock,
        sample_position: PositionSchema,
        sample_sl_order: OpenOrderSchema,
    ):
        mock_position_store.get_all.return_value = [sample_position]
        mock_order_store.get_by_position.return_value = [sample_sl_order]

        result = await service.reconcile()

        assert result.success is True
        assert any("missing take-profit" in d for d in result.discrepancies)

    async def test_reconcile_handles_exception(
        self,
        service: ReconciliationService,
        mock_exchange: AsyncMock,
    ):
        mock_exchange.get_account_info.side_effect = Exception("API Error")

        result = await service.reconcile()

        assert result.success is False
