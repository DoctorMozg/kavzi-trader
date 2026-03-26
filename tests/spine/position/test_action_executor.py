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
from kavzi_trader.spine.position.action_executor import PositionActionExecutor
from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import (
    OpenOrderSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)


@pytest.fixture
def mock_exchange() -> AsyncMock:
    exchange = AsyncMock()
    now = utc_now()
    exchange.create_order = AsyncMock(
        return_value=OrderResponseSchema(
            symbol="BTCUSDT",
            order_id=1001,
            client_order_id="test",
            transact_time=now,
            price=Decimal(48000),
            orig_qty=Decimal("0.1"),
            executed_qty=Decimal(0),
            status=OrderStatus.NEW,
            time_in_force=TimeInForce.GTC,
            type=OrderType.STOP_LOSS_LIMIT,
            side=OrderSide.SELL,
            time=now,
            update_time=now,
            is_working=False,
        ),
    )
    exchange.cancel_order = AsyncMock()
    return exchange


@pytest.fixture
def mock_state_manager() -> AsyncMock:
    state = AsyncMock()
    state.orders = AsyncMock()
    state.orders.get_by_position = AsyncMock(return_value=[])
    state.save_order = AsyncMock()
    state.remove_order = AsyncMock()
    state.remove_position = AsyncMock()
    return state


@pytest.fixture
def sample_position() -> PositionSchema:
    now = utc_now()
    return PositionSchema(
        id="pos_001",
        symbol="BTCUSDT",
        side="LONG",
        quantity=Decimal("0.1"),
        entry_price=Decimal(50000),
        stop_loss=Decimal(48000),
        take_profit=Decimal(55000),
        current_stop_loss=Decimal(48000),
        management_config=PositionManagementConfigSchema(),
        opened_at=now,
        updated_at=now,
    )


@pytest.fixture
def executor(
    mock_exchange: AsyncMock,
    mock_state_manager: AsyncMock,
) -> PositionActionExecutor:
    return PositionActionExecutor(
        exchange=mock_exchange,
        state_manager=mock_state_manager,
    )


class TestMoveStopLoss:
    async def test_cancels_old_stop_and_places_new(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        existing_sl = OpenOrderSchema(
            order_id="100",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_LOSS_LIMIT,
            price=Decimal(48000),
            quantity=Decimal("0.1"),
            status=OrderStatus.NEW,
            linked_position_id="pos_001",
            created_at=utc_now(),
        )
        mock_state_manager.orders.get_by_position.return_value = [existing_sl]
        action = PositionActionSchema(
            action=PositionActionType.MOVE_STOP_LOSS,
            new_stop_loss=Decimal(49000),
            reason="trailing stop",
        )

        await executor.execute(sample_position, action)

        mock_exchange.cancel_order.assert_called_once_with(
            symbol="BTCUSDT",
            order_id=100,
        )
        mock_state_manager.remove_order.assert_called_once_with("100")
        assert mock_exchange.create_order.call_count == 1
        call_kwargs = mock_exchange.create_order.call_args.kwargs
        assert call_kwargs["order_type"] == OrderType.STOP_LOSS_LIMIT
        assert call_kwargs["stop_price"] == Decimal(49000)

    async def test_no_op_without_new_stop_loss(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        sample_position: PositionSchema,
    ):
        action = PositionActionSchema(
            action=PositionActionType.MOVE_STOP_LOSS,
            reason="no change",
        )

        await executor.execute(sample_position, action)

        mock_exchange.create_order.assert_not_called()


class TestPartialExit:
    async def test_places_exit_and_recreates_protective(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        existing_orders = [
            OpenOrderSchema(
                order_id="200",
                symbol="BTCUSDT",
                side=OrderSide.SELL,
                order_type=OrderType.STOP_LOSS_LIMIT,
                price=Decimal(48000),
                quantity=Decimal("0.1"),
                status=OrderStatus.NEW,
                linked_position_id="pos_001",
                created_at=utc_now(),
            ),
            OpenOrderSchema(
                order_id="201",
                symbol="BTCUSDT",
                side=OrderSide.SELL,
                order_type=OrderType.TAKE_PROFIT_LIMIT,
                price=Decimal(55000),
                quantity=Decimal("0.1"),
                status=OrderStatus.NEW,
                linked_position_id="pos_001",
                created_at=utc_now(),
            ),
        ]
        mock_state_manager.orders.get_by_position.return_value = existing_orders
        action = PositionActionSchema(
            action=PositionActionType.PARTIAL_EXIT,
            exit_quantity=Decimal("0.03"),
            reason="partial take profit",
        )

        await executor.execute(sample_position, action)

        market_call = mock_exchange.create_order.call_args_list[0]
        assert market_call.kwargs["order_type"] == OrderType.MARKET
        assert market_call.kwargs["quantity"] == Decimal("0.03")
        assert mock_exchange.cancel_order.call_count == 2
        assert mock_exchange.create_order.call_count == 3


class TestFullExit:
    async def test_places_market_exit_and_removes_position(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        action = PositionActionSchema(
            action=PositionActionType.FULL_EXIT,
            reason="time exit",
        )

        await executor.execute(sample_position, action)

        mock_exchange.create_order.assert_called_once()
        call_kwargs = mock_exchange.create_order.call_args.kwargs
        assert call_kwargs["order_type"] == OrderType.MARKET
        assert call_kwargs["side"] == OrderSide.SELL
        assert call_kwargs["quantity"] == Decimal("0.1")
        mock_state_manager.remove_position.assert_called_once_with("pos_001")

    async def test_no_action_skipped(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        sample_position: PositionSchema,
    ):
        action = PositionActionSchema(
            action=PositionActionType.NO_ACTION,
            reason="no change",
        )

        await executor.execute(sample_position, action)

        mock_exchange.create_order.assert_not_called()
