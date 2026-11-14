from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ExchangeCloseSchema(BaseModel):
    """A position the exchange closed on its own (SL/TP fill or manual close)."""

    close_reason: str
    # None when the exchange gave no fill price (position found already flat).
    exit_price: Decimal | None = None

    model_config = ConfigDict(frozen=True)
