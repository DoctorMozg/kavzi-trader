import pandas as pd
from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.trend_data_schema import TrendDataSchema


class CrowdingXsDataSchema(BaseModel):
    """Daily closes and funding, plus each symbol's ls_crowding rank at each close."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    market: TrendDataSchema
    ranks: pd.DataFrame
