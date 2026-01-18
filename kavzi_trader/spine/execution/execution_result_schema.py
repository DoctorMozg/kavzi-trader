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
    executed_qty: Annotated[float, Field(default=0.0, ge=0.0)]
    executed_price: Annotated[float | None, Field(default=None)]
    error_message: Annotated[str | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)
