from decimal import Decimal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.trend_stats_schema import TrendStatsSchema
from kavzi_trader.replay.replay_llm_usage_schema import ReplayLlmUsageSchema


class ReplayResultSchema(BaseModel):
    """Account equity of one replay, sampled at each UTC midnight."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    strategy: str
    # Kline interval of the replayed bars, e.g. "4h".
    interval: str
    symbols: list[str]
    # Wallet plus unrealized PnL, indexed by the UTC day each sample closes.
    equity: pd.Series
    stats: TrendStatsSchema
    initial_equity: Decimal
    final_equity: Decimal
    funding_received: Decimal
    # Orders the spine placed, and rejected intents grouped by reason.
    orders: int
    # Intents the execution loop gave up on after retries.
    failed_decisions: int
    rejections: dict[str, int]
    # Present when the strategy asked an LLM.
    llm: ReplayLlmUsageSchema | None = None
