import pandas as pd
from pydantic import BaseModel, ConfigDict


class TrendDataSchema(BaseModel):
    """Daily closes and per-day summed funding, one column per symbol."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    closes: pd.DataFrame
    funding: pd.DataFrame
