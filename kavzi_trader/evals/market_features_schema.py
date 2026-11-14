from typing import Annotated

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field


class MarketFeaturesSchema(BaseModel):
    """Per-bar ATR(14), its rolling z-score and the regime index (REGIME_ORDER)."""

    atr: Annotated[NDArray[np.float64], Field(...)]
    atr_zscore: Annotated[NDArray[np.float64], Field(...)]
    regime_code: Annotated[NDArray[np.int8], Field(...)]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
