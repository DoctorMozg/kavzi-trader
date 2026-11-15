import pandas as pd

from kavzi_trader.evals.case_result_schema import CaseResultSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.joined_case_schema import JoinedCaseSchema
from kavzi_trader.evals.stage_metrics_schema import StageMetricsSchema
from kavzi_trader.evals.trader_record_schema import TraderRecordSchema
from tests.evals.eval_fixtures import SYMBOL, case_at
from tests.evals.frames import make_frame

DECISION = 10
ENTRY = 100.0


def flat_frame(bars: int = 130) -> pd.DataFrame:
    """Candles pinned at 100 so a test controls exactly which bar touches what."""
    frame = make_frame(bars)
    for column in ("open", "high", "low", "close"):
        frame[column] = ENTRY
    return frame


def trader_record(
    action: str = "LONG",
    *,
    sl: float | None = 98.0,
    tp: float | None = 104.0,
    stop_reason: str = "ok",
    metrics: StageMetricsSchema | None = None,
) -> TraderRecordSchema:
    return TraderRecordSchema(
        action=action,
        entry=ENTRY,
        stop_loss=sl,
        take_profit=tp,
        stop_reason=stop_reason,
        metrics=metrics or StageMetricsSchema(requests=1),
    )


def joined(
    case: EvalCaseSchema,
    stopped_at: str,
    trader: TraderRecordSchema | None = None,
    *,
    bypassed: bool = False,
    forced: bool = False,
) -> JoinedCaseSchema:
    result = CaseResultSchema.model_validate(
        {
            "case_id": case.case_id,
            "status": "ok",
            "label": case.label.value,
            "regime": case.regime,
            "tier": case.tier,
            "scout_verdict": "SKIP" if bypassed else "INTERESTING",
            "scout_bypassed": bypassed,
            "stopped_at": stopped_at,
            "trader_forced": forced,
            "trader": trader,
        }
    )
    return JoinedCaseSchema(result=result, case=case)


def case_for(
    frame: pd.DataFrame, label: str = "LONG", **overrides: object
) -> EvalCaseSchema:
    return case_at(frame, DECISION, label=label, symbol=SYMBOL, **overrides)
