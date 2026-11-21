import pandas as pd
from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.bar_quality_schema import BarQualitySchema


class IntradayDataSchema(BaseModel):
    """Bar closes of ``hours`` bars, ``24 / hours`` per daily row, a column per symbol.

    The index is the bar open time. The last bar of each UTC day carries that
    day's close from the daily data; days a symbol is not traded are NaN.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    hours: int
    bars: pd.DataFrame
    quality: BarQualitySchema
