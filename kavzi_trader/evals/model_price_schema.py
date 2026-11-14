from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ModelPriceSchema(BaseModel):
    """List price in USD per million tokens."""

    input_per_mtok: Annotated[Decimal, Field(..., ge=0)]
    output_per_mtok: Annotated[Decimal, Field(..., ge=0)]
    cache_read_per_mtok: Annotated[Decimal, Field(..., ge=0)]
    cache_write_per_mtok: Annotated[Decimal, Field(..., ge=0)]

    model_config = ConfigDict(frozen=True)
