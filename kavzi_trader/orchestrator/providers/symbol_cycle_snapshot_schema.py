from pydantic import BaseModel, ConfigDict

from kavzi_trader.domain.algorithm_confluence import DualConfluenceSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.indicators.htf import HtfTrendSchema


class SymbolCycleSnapshotSchema(BaseModel):
    """Per-symbol values computed once per reasoning cycle, then reused.

    Mutable on purpose: fields fill in lazily as the pipeline stages ask for them.
    """

    regime: VolatilityRegime | None = None
    confluence: DualConfluenceSchema | None = None
    htf_trend: HtfTrendSchema | None = None

    model_config = ConfigDict(frozen=False)
