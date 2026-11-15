from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.barrier_enums import BarrierOutcome


class SimTradeSchema(BaseModel):
    """One Trader trade walked forward over real candles."""

    case_id: Annotated[str, Field(...)]
    label: Annotated[str, Field(...)]
    regime: Annotated[str, Field(...)]
    tier: Annotated[str, Field(...)]
    side: Annotated[str, Field(...)]
    outcome: Annotated[BarrierOutcome, Field(...)]
    r_multiple: Annotated[float, Field(...)]

    model_config = ConfigDict(frozen=True)
