from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.analyst_record_schema import AnalystRecordSchema
from kavzi_trader.evals.trader_record_schema import TraderRecordSchema

StopStage = Literal[
    "scout",
    "analyst_skipped",
    "analyst_error",
    "analyst_gate",
    "trader_gate",
    "trader_error",
    "trader",
]


class CaseResultSchema(BaseModel):
    """One JSONL line: what each Brain stage did for one case."""

    case_id: Annotated[str, Field(...)]
    status: Annotated[Literal["ok", "error"], Field(...)]
    error: str | None = None
    label: Annotated[str, Field(...)]
    regime: Annotated[str, Field(...)]
    tier: Annotated[str, Field(...)]
    rebuilt_regime: str | None = None
    scout_verdict: str | None = None
    scout_reason: str | None = None
    scout_pattern: str | None = None
    scout_bypassed: bool = False
    # Last stage that acted; "trader" means the Trader produced the final word.
    stopped_at: StopStage | None = None
    analyst: AnalystRecordSchema | None = None
    trader: TraderRecordSchema | None = None

    model_config = ConfigDict(frozen=True)
