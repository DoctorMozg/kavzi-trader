from decimal import Decimal

import pytest

from kavzi_trader.api.common.models import OrderSide, OrderType
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    OpenOrderSchema,
    PositionManagementConfigSchema,
    PositionSchema,
    ReconciliationResultSchema,
)


class TestPositionManagementConfigSchema:
    def test_default_values(self):
        config = PositionManagementConfigSchema()
        assert config.trailing_stop_atr_multiplier == Decimal("1.5")
        assert config.trailing_stop_trigger_atr == Decimal("2.0")
        assert config.break_even_trigger_atr == Decimal("1.5")
        assert config.break_even_buffer_atr == Decimal("0.3")
        assert config.break_even_min_hold_s == 900
        assert config.partial_exit_at_fraction == Decimal("0.65")
        assert config.partial_exit_size == Decimal("0.3")
        assert config.partial_exit_min_profit_atr == Decimal("1.0")
        assert config.max_hold_time_hours == 24

    def test_custom_values(self):
        config = PositionManagementConfigSchema(
            trailing_stop_atr_multiplier=Decimal("2.0"),
        )
        assert config.trailing_stop_atr_multiplier == Decimal("2.0")

    def test_frozen(self):
        from pydantic import ValidationError

        config = PositionManagementConfigSchema()
        with pytest.raises(ValidationError):
            config.max_hold_time_hours = 48


class TestPositionSchema:
    def test_create_long_position(self, sample_position: PositionSchema):
        assert sample_position.id == "pos_123"
        assert sample_position.symbol == "BTCUSDT"
        assert sample_position.side == "LONG"
        assert sample_position.quantity == Decimal("0.1")
        assert sample_position.entry_price == Decimal(50000)
        assert sample_position.stop_loss_moved_to_breakeven is False

    def test_create_short_position(self, sample_position_short: PositionSchema):
        assert sample_position_short.side == "SHORT"
        assert sample_position_short.symbol == "ETHUSDT"

    def test_serialization_roundtrip(self, sample_position: PositionSchema):
        json_str = sample_position.model_dump_json()
        restored = PositionSchema.model_validate_json(json_str)
        assert restored.id == sample_position.id
        assert restored.quantity == sample_position.quantity


class TestOpenOrderSchema:
    def test_create_order(self, sample_order: OpenOrderSchema):
        assert sample_order.order_id == "order_789"
        assert sample_order.symbol == "BTCUSDT"
        assert sample_order.side == OrderSide.BUY
        assert sample_order.order_type == OrderType.LIMIT
        assert sample_order.executed_qty == Decimal(0)

    def test_sl_order(self, sample_sl_order: OpenOrderSchema):
        assert sample_sl_order.order_type == OrderType.STOP_MARKET
        assert sample_sl_order.linked_position_id == "pos_123"

    def test_serialization_roundtrip(self, sample_order: OpenOrderSchema):
        json_str = sample_order.model_dump_json()
        restored = OpenOrderSchema.model_validate_json(json_str)
        assert restored.order_id == sample_order.order_id
        assert restored.side == sample_order.side


class TestAccountStateSchema:
    def test_create_account_state(self, sample_account_state: AccountStateSchema):
        assert sample_account_state.total_balance_usdt == Decimal(10000)
        assert sample_account_state.available_balance_usdt == Decimal(9000)
        assert sample_account_state.locked_balance_usdt == Decimal(1000)

    def test_drawdown_calculation(self):
        state = AccountStateSchema(
            total_balance_usdt=Decimal(9500),
            available_balance_usdt=Decimal(9500),
            locked_balance_usdt=Decimal(0),
            peak_balance=Decimal(10000),
            current_drawdown_percent=Decimal("5.0"),
            updated_at=utc_now(),
        )
        assert state.current_drawdown_percent == Decimal("5.0")


class TestReconciliationResultSchema:
    def test_success_result(self):
        result = ReconciliationResultSchema(
            success=True,
            discrepancies=[],
            positions_synced=2,
            orders_synced=4,
        )
        assert result.success is True
        assert result.positions_synced == 2

    def test_failure_result(self):
        result = ReconciliationResultSchema(
            success=False,
            discrepancies=["Missing SL order", "Unknown order on exchange"],
        )
        assert result.success is False
        assert len(result.discrepancies) == 2
