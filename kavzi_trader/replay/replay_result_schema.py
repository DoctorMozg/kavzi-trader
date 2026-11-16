from decimal import Decimal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.trend_stats_schema import TrendStatsSchema


class ReplayResultSchema(BaseModel):
    """Account equity of one replay, sampled at each UTC midnight."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    strategy: str
    symbols: list[str]
    # Wallet plus unrealized PnL, indexed by the UTC day each sample closes.
    equity: pd.Series
    stats: TrendStatsSchema
    initial_equity: Decimal
    final_equity: Decimal
    funding_received: Decimal
    # Orders the spine placed, and rejected intents grouped by reason.
    orders: int
    rejections: dict[str, int]
