from datetime import datetime
from decimal import Decimal
from typing import TypedDict

from kavzi_trader.brain.context.confluence_trimmer import ConfluenceBlockDict
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema

__all__ = [
    "ATRFallbackTargetDict",
    "AccountStateDict",
    "AnalystContextDict",
    "ConfluenceBlockDict",
    "MarketContextDict",
    "SystemPromptContextDict",
    "TraderContextDict",
]


class AccountStateDict(TypedDict):
    """Serialized shape of ``AccountStateSchema.model_dump()``.

    Produced via ``deps.account_state.model_dump()`` in the trader
    context builder and consumed by ``user/context/account_state.j2``
    and ``user/requests/make_decision.j2``. Kept distinct from the
    Binance REST ``AccountInfoDict`` (external API shape) because this
    mirrors our internal ``AccountStateSchema`` fields.
    """

    total_balance_usdt: Decimal
    available_balance_usdt: Decimal
    locked_balance_usdt: Decimal
    unrealized_pnl: Decimal
    peak_balance: Decimal
    current_drawdown_percent: Decimal
    total_margin_balance: Decimal
    margin_ratio: Decimal
    updated_at: datetime


class ATRFallbackTargetDict(TypedDict):
    """Single ATR-projected take-profit target.

    Produced by ``ContextBuilder._compute_atr_fallback_targets`` and
    consumed by ``user/context/analyst_result.j2`` where each entry is
    rendered as ``{{ target.label }} @ {{ target.price }}``.
    """

    price: str
    label: str


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
    algorithm_confluence_long: ConfluenceBlockDict | None
    algorithm_confluence_short: ConfluenceBlockDict | None
    detected_side: str
    futures_leverage: int
    symbol_tier: str
    tier_min_confidence: str
    # Regime-specific minimum raw confluence score required to escalate
    # to the Trader tier. The system prompt publishes the NORMAL baseline;
    # this per-request field overrides it with the gate for the current
    # volatility regime (NORMAL=6, HIGH=7, EXTREME=8, LOW=7), scaled down
    # when some algorithm signals have no input.
    confluence_enter_min: int
    counter_trend_gate_bump: int
    available_signals: int
    max_confluence_score: int
    sentiment_summary: str | None
    sentiment_bias: str | None
    sentiment_confidence_adjustment: str | None
    htf_trend: str | None


class TraderContextDict(MarketContextDict):
    """Template context for the trader agent."""

    order_flow_compact: str | None
    algorithm_confluence_long: ConfluenceBlockDict | None
    algorithm_confluence_short: ConfluenceBlockDict | None
    detected_side: str
    account_state: AccountStateDict
    analyst_result: AnalystDecisionSchema | None
    futures_leverage: int
    liquidation_distance_percent: float
    open_positions_json: str
    funding_rate_24h_percent: str | None
    scout_pattern: str | None
    symbol_tier: str
    tier_min_confidence: str
    confluence_enter_min: int
    available_signals: int
    high_confluence_min: int
    breakout_algo_min: int
    sentiment_summary: str | None
    sentiment_bias: str | None
    sentiment_confidence_adjustment: str | None
    atr_fallback_targets: list[ATRFallbackTargetDict]


class RegimeGateDict(TypedDict):
    """One regime's raw-confluence entry gate, as rendered in prompts."""

    regime: str
    gate: int


class SystemPromptContextDict(TypedDict):
    """Config values injected into system prompt templates."""

    min_rr_ratio: str
    drawdown_pause_percent: str
    drawdown_close_all_percent: str
    regime_gates: list[RegimeGateDict]
    counter_trend_gate_bump: int
    max_tp_atr: str
    max_stop_atr: str
    volatility_low_threshold: str
    volatility_high_threshold: str
    volatility_extreme_threshold: str
    tier_1_min_confidence: str
    tier_2_min_confidence: str
    tier_3_min_confidence: str
    analyst_reasoning_max_chars: int
    trader_reasoning_max_chars: int
    key_level_reason_max_chars: int
    max_key_levels: int
