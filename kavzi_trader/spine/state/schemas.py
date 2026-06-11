from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.api.common.models import OrderSide, OrderStatus, OrderType


class PositionManagementConfigSchema(BaseModel):
    partial_exit_at_fraction: Annotated[
        Decimal, Field(ge=Decimal(0), le=Decimal(1))
    ] = Decimal("0.65")
    partial_exit_size: Decimal = Decimal("0.3")
    partial_exit_min_profit_atr: Decimal = Decimal("1.0")
    max_hold_time_hours: int = 24
    # Exit if position hasn't moved stall_min_progress_atr in ATR units toward
    # TP after stall_check_after_hours. Catches setups that were wrong but
    # didn't trigger the stop-loss.
    stall_check_after_hours: int = 8
    stall_min_progress_atr: Decimal = Decimal("0.3")

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
    atr_at_entry: Decimal | None = None
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


class PendingEntrySchema(BaseModel):
    """A resting PULLBACK entry limit awaiting fill or expiry.

    ``decision_json`` is the serialized ``DecisionMessageSchema`` that placed
    the order — stored as a string to keep this state schema free of an
    import cycle with the execution layer. The engine re-parses it to open
    and protect the position once the limit fills.
    """

    order_id: str
    symbol: str
    decision_json: str
    expires_at_ms: int

    model_config = ConfigDict(frozen=True)


class AccountStateSchema(BaseModel):
    total_balance_usdt: Decimal
    available_balance_usdt: Decimal
    locked_balance_usdt: Decimal
    unrealized_pnl: Decimal = Decimal(0)
    peak_balance: Decimal
    # Timestamp of the last peak_balance derivation. Drives the time-based
    # peak decay in AccountStore.update_balance so drawdown recovers when the
    # balance stays flat below the peak. Defaults to None so Redis records
    # written before this field deserialize cleanly.
    peak_balance_updated_at: Annotated[datetime | None, Field(default=None)] = None
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
