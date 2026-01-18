from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.api.common.models import OrderSide, OrderType, TimeInForce


class OrderRequestSchema(BaseModel):
    """Exchange order request derived from a decision."""

    symbol: Annotated[str, Field(...)]
    side: Annotated[OrderSide, Field(...)]
    order_type: Annotated[OrderType, Field(...)]
    quantity: Annotated[Decimal, Field(...)]
    price: Annotated[Decimal | None, Field(default=None)]
    time_in_force: Annotated[TimeInForce | None, Field(default=None)]
    stop_price: Annotated[Decimal | None, Field(default=None)]
    client_order_id: Annotated[str | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)
