from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.evals.validation.paired_sharpe_schema import PairedSharpeSchema


class CombinedArmsResultSchema(BaseModel):
    """The four exit and halving arms over the same days, with their paired tests."""

    model_config = ConfigDict(frozen=True)

    base: TrendResultSchema
    mid: TrendResultSchema
    halving: TrendResultSchema
    mid_halving: TrendResultSchema
    # Symbol-days with a spike while held, under the base and the mid-exit book.
    spike_days_base: int
    spike_days_mid: int
    mid_gain_with_halving: PairedSharpeSchema
    mid_gain_alone: PairedSharpeSchema
    halving_change_under_mid: PairedSharpeSchema
    halving_change_under_base: PairedSharpeSchema
    combined_vs_base: PairedSharpeSchema
