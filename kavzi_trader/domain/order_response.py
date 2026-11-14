from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.domain.order_enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)


class OrderFillSchema(BaseModel):
    """Information about a fill for an order."""

    price: Decimal
    qty: Decimal
    commission: Decimal
    commission_asset: str
    trade_id: int | None = None

    model_config = ConfigDict(frozen=True)


class OrderResponseSchema(BaseModel):
    """Response for order creation or query."""

    symbol: str
    order_id: int
    client_order_id: str
    transact_time: datetime
    price: Decimal
    orig_qty: Decimal
    executed_qty: Decimal
    status: OrderStatus
    time_in_force: TimeInForce
    type: OrderType
    side: OrderSide
    fills: list[OrderFillSchema] = Field(default_factory=list)
    # Optional fields
    stop_price: Decimal | None = None
    # Futures REST reports the real fill price here; `price` is 0 for MARKET.
    avg_price: Decimal | None = None
    iceberg_qty: Decimal | None = None
    time: datetime | None = None
    update_time: datetime | None = None
    is_working: bool | None = None
    orig_quote_order_qty: Decimal | None = None
    # Futures-specific fields
    reduce_only: bool = False
    position_side: str | None = None
    close_position: bool = False

    model_config = ConfigDict(frozen=True)

    @property
    def effective_fill_price(self) -> Decimal | None:
        """Weighted-average fill price, or None when the exchange gave none."""
        if self.avg_price is not None and self.avg_price > 0:
            return self.avg_price
        total_qty = sum((f.qty for f in self.fills), Decimal(0))
        if total_qty > 0:
            weighted = sum((f.price * f.qty for f in self.fills), Decimal(0))
            return weighted / total_qty
        return self.price if self.price > 0 else None
