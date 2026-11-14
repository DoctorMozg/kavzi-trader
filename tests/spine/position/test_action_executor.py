from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.exceptions import ExchangeError
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
            type=OrderType.STOP_MARKET,
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
                order_type=OrderType.STOP_MARKET,
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
                order_type=OrderType.TAKE_PROFIT_MARKET,
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

    async def test_success_persists_reduced_quantity_and_flag_once(
        self,
        executor: PositionActionExecutor,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        action = PositionActionSchema(
            action=PositionActionType.PARTIAL_EXIT,
            exit_quantity=Decimal("0.03"),
            reason="partial take profit",
        )

        await executor.execute(sample_position, action)

        mock_state_manager.update_position.assert_called_once()
        saved = mock_state_manager.update_position.call_args.args[0]
        assert saved.quantity == Decimal("0.07")
        assert saved.partial_exit_done is True

    async def test_failed_exit_order_leaves_state_untouched(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        mock_exchange.create_order.side_effect = RuntimeError("exchange down")
        action = PositionActionSchema(
            action=PositionActionType.PARTIAL_EXIT,
            exit_quantity=Decimal("0.03"),
            reason="partial take profit",
        )

        await executor.execute(sample_position, action)

        mock_state_manager.update_position.assert_not_called()
        mock_exchange.cancel_order.assert_not_called()

    async def test_protective_replacement_failure_keeps_reduced_quantity(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        mock_exchange.create_order.side_effect = [
            mock_exchange.create_order.return_value,
            RuntimeError("stop rejected"),
            mock_exchange.create_order.return_value,
        ]
        action = PositionActionSchema(
            action=PositionActionType.PARTIAL_EXIT,
            exit_quantity=Decimal("0.03"),
            reason="partial take profit",
        )

        await executor.execute(sample_position, action)

        saved = mock_state_manager.update_position.call_args.args[0]
        assert saved.quantity == Decimal("0.07")
        assert saved.partial_exit_done is True
        # TP is still attempted after the stop failed
        assert mock_exchange.create_order.call_count == 3


class TestCancelLinkedOrders:
    async def test_unknown_order_error_removes_local_order(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        mock_state_manager.orders.get_by_position.return_value = [
            OpenOrderSchema(
                order_id="200",
                symbol="BTCUSDT",
                side=OrderSide.SELL,
                order_type=OrderType.STOP_MARKET,
                price=Decimal(48000),
                quantity=Decimal("0.1"),
                status=OrderStatus.NEW,
                linked_position_id="pos_001",
                created_at=utc_now(),
            ),
        ]
        mock_exchange.cancel_order.side_effect = ExchangeError(
            "Unknown order sent.",
            code=-2011,
        )

        await executor._cancel_linked_orders(sample_position)

        mock_state_manager.remove_order.assert_called_once_with("200")


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

    async def test_returns_avg_fill_price_when_order_price_is_zero(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        sample_position: PositionSchema,
    ):
        now = utc_now()
        mock_exchange.create_order.return_value = OrderResponseSchema(
            symbol="BTCUSDT",
            order_id=1002,
            client_order_id="exit",
            transact_time=now,
            price=Decimal(0),
            avg_price=Decimal("51234.5"),
            orig_qty=Decimal("0.1"),
            executed_qty=Decimal("0.1"),
            status=OrderStatus.FILLED,
            time_in_force=TimeInForce.GTC,
            type=OrderType.MARKET,
            side=OrderSide.SELL,
        )
        action = PositionActionSchema(
            action=PositionActionType.FULL_EXIT,
            reason="time exit",
        )

        exit_price = await executor.execute(sample_position, action)

        assert exit_price == Decimal("51234.5")

    async def test_unknown_fill_price_is_not_reported_as_zero(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        sample_position: PositionSchema,
    ):
        mock_exchange.create_order.return_value = (
            mock_exchange.create_order.return_value.model_copy(
                update={"price": Decimal(0)},
            )
        )
        action = PositionActionSchema(
            action=PositionActionType.FULL_EXIT,
            reason="time exit",
        )

        exit_price = await executor.execute(sample_position, action)

        assert exit_price is None

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


def _linked(order_type: OrderType, order_id: str = "300") -> OpenOrderSchema:
    return OpenOrderSchema(
        order_id=order_id,
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=order_type,
        price=Decimal(55000),
        quantity=Decimal("0.1"),
        status=OrderStatus.NEW,
        linked_position_id="pos_001",
        created_at=utc_now(),
    )


def _exchange_order(
    order_type: OrderType,
    stop_price: Decimal,
    order_id: int = 777,
) -> OrderResponseSchema:
    now = utc_now()
    return OrderResponseSchema(
        symbol="BTCUSDT",
        order_id=order_id,
        client_order_id="x",
        transact_time=now,
        price=Decimal(0),
        orig_qty=Decimal("0.1"),
        executed_qty=Decimal(0),
        status=OrderStatus.NEW,
        time_in_force=TimeInForce.GTC,
        type=order_type,
        side=OrderSide.SELL,
        stop_price=stop_price,
        time=now,
    )


class TestRetryMissingTakeProfit:
    async def test_places_take_profit_when_none_exists(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        mock_exchange.get_open_orders = AsyncMock(return_value=[])

        await executor.retry_missing_take_profit(sample_position)

        kwargs = mock_exchange.create_order.call_args.kwargs
        assert kwargs["order_type"] == OrderType.TAKE_PROFIT_MARKET
        assert kwargs["stop_price"] == Decimal(55000)
        assert kwargs["reduce_only"] is True
        mock_state_manager.save_order.assert_called_once()

    async def test_does_nothing_when_take_profit_is_already_linked(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        mock_state_manager.orders.get_by_position.return_value = [
            _linked(OrderType.TAKE_PROFIT_MARKET),
        ]

        await executor.retry_missing_take_profit(sample_position)

        mock_exchange.create_order.assert_not_called()

    async def test_adopts_take_profit_already_resting_on_exchange(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        # The first placement reached the exchange but saving it locally failed.
        mock_exchange.get_open_orders = AsyncMock(
            return_value=[
                _exchange_order(OrderType.TAKE_PROFIT_MARKET, Decimal(55000)),
            ],
        )

        await executor.retry_missing_take_profit(sample_position)

        mock_exchange.create_order.assert_not_called()
        saved = mock_state_manager.save_order.call_args.args[0]
        assert saved.order_id == "777"
        assert saved.linked_position_id == "pos_001"

    async def test_placement_failure_propagates(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        sample_position: PositionSchema,
    ):
        mock_exchange.get_open_orders = AsyncMock(return_value=[])
        mock_exchange.create_order.side_effect = ExchangeError("nope", code=-1021)

        with pytest.raises(ExchangeError):
            await executor.retry_missing_take_profit(sample_position)


class TestSweepOrphanedOrders:
    async def test_cancels_only_orders_of_vanished_positions(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
        sample_position: PositionSchema,
    ):
        orphan = _linked(OrderType.STOP_MARKET, "301").model_copy(
            update={"linked_position_id": "gone"},
        )
        mock_state_manager.get_open_orders = AsyncMock(
            return_value=[
                orphan,
                _linked(OrderType.STOP_MARKET, "302"),
                _linked(OrderType.LIMIT, "303").model_copy(
                    update={"linked_position_id": None},
                ),
            ],
        )
        mock_state_manager.get_all_positions = AsyncMock(
            return_value=[sample_position],
        )

        await executor.sweep_orphaned_orders()

        mock_exchange.cancel_order.assert_awaited_once_with(
            symbol="BTCUSDT",
            order_id=301,
        )
        mock_state_manager.remove_order.assert_awaited_once_with("301")

    async def test_failed_cancel_keeps_the_record_for_the_next_sweep(
        self,
        executor: PositionActionExecutor,
        mock_exchange: AsyncMock,
        mock_state_manager: AsyncMock,
    ):
        orphan = _linked(OrderType.STOP_MARKET, "301")
        mock_state_manager.get_open_orders = AsyncMock(return_value=[orphan])
        mock_state_manager.get_all_positions = AsyncMock(return_value=[])
        mock_exchange.cancel_order.side_effect = [
            ExchangeError("timeout", code=-1007),
            None,
        ]

        await executor.sweep_orphaned_orders()
        mock_state_manager.remove_order.assert_not_called()
        await executor.sweep_orphaned_orders()

        mock_state_manager.remove_order.assert_awaited_once_with("301")
