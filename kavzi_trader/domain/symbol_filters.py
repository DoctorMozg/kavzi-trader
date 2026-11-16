from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class SymbolFiltersSchema(BaseModel):
    """Order-size and price grid of one futures symbol, from exchangeInfo."""

    symbol: str
    step_size: Annotated[Decimal, Field(gt=0)]
    min_qty: Annotated[Decimal, Field(ge=0)]
    max_qty: Annotated[Decimal, Field(gt=0)]
    market_step_size: Annotated[Decimal, Field(gt=0)]
    market_min_qty: Annotated[Decimal, Field(ge=0)]
    market_max_qty: Annotated[Decimal, Field(gt=0)]
    tick_size: Annotated[Decimal, Field(gt=0)]
    min_notional: Annotated[Decimal, Field(ge=0)]

    model_config = ConfigDict(frozen=True)
