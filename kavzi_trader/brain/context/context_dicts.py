from typing import Any, TypedDict

from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema


class MarketContextDict(TypedDict):
    """Base context shared by analyst and trader templates.

    The prior design also serialized a full ``market_snapshot`` dict via
    ``model_dump()``. It duplicated data already present in
    ``candles_table`` and ``indicators_compact`` and inflated the Analyst
    prompt by ~5k tokens per request. Replaced by flat scalars below.
    """

    candles_table: str
    indicators_compact: str
    symbol: str
    timeframe: str
    current_price: str
    volatility_regime: str
    atr_14: str | None


class AnalystContextDict(MarketContextDict):
    """Template context for the analyst agent."""

    order_flow_compact: str | None
    # LONG / SHORT confluence blocks are side-trimmed based on
    # ``detected_side``. Whichever side is NOT the detected direction is
    # dropped to ``None`` when the LLM only needs one perspective.
    algorithm_confluence_long: dict[str, Any] | None
    algorithm_confluence_short: dict[str, Any] | None
    detected_side: str
    futures_leverage: int
    symbol_tier: str
    tier_min_confidence: str
    # Regime-specific minimum raw confluence score required to escalate
    # to the Trader tier. The system prompt publishes the NORMAL baseline;
    # this per-request field overrides it with the gate for the current
    # volatility regime (NORMAL=6, HIGH=7, EXTREME=8, LOW=7).
    confluence_enter_min: int
    sentiment_summary: str | None
    sentiment_bias: str | None
    sentiment_confidence_adjustment: str | None


class TraderContextDict(MarketContextDict):
    """Template context for the trader agent."""

    order_flow_compact: str | None
    algorithm_confluence_long: dict[str, Any] | None
    algorithm_confluence_short: dict[str, Any] | None
    detected_side: str
    account_state: dict[str, Any]
    analyst_result: AnalystDecisionSchema | None
    futures_leverage: int
    liquidation_distance_percent: float
    open_positions_json: str
    funding_rate_24h_percent: str | None
    scout_pattern: str | None
    symbol_tier: str
    tier_min_confidence: str
    sentiment_summary: str | None
    sentiment_bias: str | None
    sentiment_confidence_adjustment: str | None
    atr_fallback_targets: list[dict[str, str]]


class SystemPromptContextDict(TypedDict):
    """Config values injected into system prompt templates."""

    min_rr_ratio: str
    drawdown_pause_percent: str
    drawdown_close_all_percent: str
    confluence_enter_min: int
    volatility_low_threshold: str
    volatility_high_threshold: str
    volatility_extreme_threshold: str
    tier_1_min_confidence: str
    tier_2_min_confidence: str
    tier_3_min_confidence: str
