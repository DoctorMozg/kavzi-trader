from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ClassMetricsSchema(BaseModel):
    """One class of the confusion matrix; a rate is None when its denominator is 0."""

    support: Annotated[int, Field(ge=0)]
    predicted: Annotated[int, Field(ge=0)]
    hits: Annotated[int, Field(ge=0)]
    precision: float | None
    recall: float | None
    f1: float | None

    model_config = ConfigDict(frozen=True)
