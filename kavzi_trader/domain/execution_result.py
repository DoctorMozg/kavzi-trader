from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExecutionResultSchema(BaseModel):
    """Represents the outcome of an execution attempt."""

    decision_id: Annotated[str, Field(...)]
    order_id: Annotated[str | None, Field(default=None)]
    status: Annotated[
        Literal["SUBMITTED", "FILLED", "PARTIAL", "REJECTED", "EXPIRED"],
        Field(...),
    ]
    executed_qty: Annotated[Decimal | None, Field(default=None)]
    executed_price: Annotated[Decimal | None, Field(default=None)]
    error_message: Annotated[str | None, Field(default=None)]
    needs_reconciliation: Annotated[bool, Field(default=False)]

    model_config = ConfigDict(frozen=True)
