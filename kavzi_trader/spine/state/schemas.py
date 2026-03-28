from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from kavzi_trader.api.common.models import OrderSide, OrderStatus, OrderType


class PositionManagementConfigSchema(BaseModel):
    trailing_stop_atr_multiplier: Decimal = Decimal("1.5")
    trailing_stop_trigger_atr: Decimal = Decimal("2.0")
    break_even_trigger_atr: Decimal = Decimal("1.5")
    break_even_min_hold_s: int = 900
    partial_exit_at_percent: Decimal = Decimal("0.65")
    partial_exit_size: Decimal = Decimal("0.3")
    partial_exit_min_profit_atr: Decimal = Decimal("1.0")
    max_hold_time_hours: int = 24

    model_config = ConfigDict(frozen=True)


class PositionSchema(BaseModel):
    id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: Decimal
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    current_stop_loss: Decimal
    management_config: PositionManagementConfigSchema
    leverage: int = 1
    liquidation_price: Decimal | None = None
    initial_margin: Decimal = Decimal(0)
    unrealized_pnl: Decimal = Decimal(0)
    accumulated_funding: Decimal = Decimal(0)
    stop_loss_moved_to_breakeven: bool = False
    partial_exit_done: bool = False
    opened_at: datetime
    updated_at: datetime

    model_config = ConfigDict(frozen=True)


class OpenOrderSchema(BaseModel):
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Decimal
    quantity: Decimal
    executed_qty: Decimal = Decimal(0)
    status: OrderStatus
    linked_position_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(frozen=True)


class AccountStateSchema(BaseModel):
    total_balance_usdt: Decimal
    available_balance_usdt: Decimal
    locked_balance_usdt: Decimal
    unrealized_pnl: Decimal = Decimal(0)
    peak_balance: Decimal
    current_drawdown_percent: Decimal = Decimal(0)
    total_margin_balance: Decimal = Decimal(0)
    margin_ratio: Decimal = Decimal(0)
    updated_at: datetime

    model_config = ConfigDict(frozen=True)


class ReconciliationResultSchema(BaseModel):
    success: bool
    discrepancies: list[str]
    positions_synced: int = 0
    orders_synced: int = 0
    orders_removed: int = 0

    model_config = ConfigDict(frozen=True)
