"""Events the trader publishes to the dashboard; this is the UI wire contract."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PositionSide = Literal["LONG", "SHORT"]
DecisionStage = Literal[
    "scout", "analyst", "trader", "filter", "position", "trend", "gate", "execution"
]

# Defaults are always serialized, so the TS types must not mark them optional.
UI_MODEL_CONFIG = ConfigDict(
    frozen=True, json_schema_serialization_defaults_required=True
)


class UiOpenPositionSchema(BaseModel):
    id: Annotated[str, Field(...)]
    symbol: Annotated[str, Field(...)]
    side: Annotated[PositionSide, Field(...)]
    quantity: Annotated[Decimal, Field(...)]
    entry_price: Annotated[Decimal, Field(...)]
    mark_price: Annotated[Decimal, Field(...)]
    stop_loss: Annotated[Decimal, Field(...)]
    take_profit: Annotated[Decimal | None, Field()] = None
    unrealized_pnl_usdt: Annotated[Decimal, Field(...)]
    leverage: Annotated[int, Field(..., ge=1)]
    opened_at_ms: Annotated[int, Field(..., ge=0)]

    model_config = UI_MODEL_CONFIG


class UiCandleSchema(BaseModel):
    open_time_ms: Annotated[int, Field(..., ge=0)]
    open: Annotated[Decimal, Field(...)]
    high: Annotated[Decimal, Field(...)]
    low: Annotated[Decimal, Field(...)]
    close: Annotated[Decimal, Field(...)]
    volume: Annotated[Decimal, Field(...)]

    model_config = UI_MODEL_CONFIG


class UiAccountEventSchema(BaseModel):
    """Periodic full account state; session fields repeat so trimming is safe."""

    type: Annotated[Literal["account"], Field()] = "account"
    ts_ms: Annotated[int, Field(..., ge=0)]
    session_started_at_ms: Annotated[int, Field(..., ge=0)]
    is_paper: Annotated[bool, Field(...)]
    initial_balance_usdt: Annotated[Decimal, Field(...)]
    balance_usdt: Annotated[Decimal, Field(...)]
    unrealized_pnl_usdt: Annotated[Decimal, Field(...)]
    positions: Annotated[list[UiOpenPositionSchema], Field()] = Field(
        default_factory=list
    )
    prices: Annotated[dict[str, Decimal], Field()] = Field(default_factory=dict)
    running_loops: Annotated[list[str], Field()] = Field(default_factory=list)

    model_config = UI_MODEL_CONFIG


class UiDecisionEventSchema(BaseModel):
    """One step of the Scout -> Analyst -> Trader pipeline or a position action."""

    type: Annotated[Literal["decision"], Field()] = "decision"
    event_id: Annotated[str, Field()] = Field(default_factory=lambda: uuid4().hex)
    ts_ms: Annotated[int, Field(..., ge=0)]
    symbol: Annotated[str, Field(...)]
    stage: Annotated[DecisionStage, Field(...)]
    verdict: Annotated[str, Field(..., min_length=1)]
    summary: Annotated[str, Field(...)]
    reasoning: Annotated[str | None, Field()] = None
    confidence: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    latency_ms: Annotated[int | None, Field(ge=0)] = None

    model_config = UI_MODEL_CONFIG


class UiTradeEventSchema(BaseModel):
    type: Annotated[Literal["trade"], Field()] = "trade"
    event_id: Annotated[str, Field()] = Field(default_factory=lambda: uuid4().hex)
    ts_ms: Annotated[int, Field(..., ge=0)]
    symbol: Annotated[str, Field(...)]
    side: Annotated[Literal["LONG", "SHORT", "CLOSE"], Field(...)]
    status: Annotated[str, Field(...)]
    # None for rule-based trades, which have no model confidence.
    confidence: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    entry_price: Annotated[Decimal | None, Field()] = None
    quantity: Annotated[Decimal | None, Field()] = None
    stop_loss: Annotated[Decimal | None, Field()] = None
    take_profit: Annotated[Decimal | None, Field()] = None
    reasoning: Annotated[str, Field()] = ""

    model_config = UI_MODEL_CONFIG


class UiPositionClosedEventSchema(BaseModel):
    type: Annotated[Literal["position_closed"], Field()] = "position_closed"
    event_id: Annotated[str, Field()] = Field(default_factory=lambda: uuid4().hex)
    ts_ms: Annotated[int, Field(..., ge=0)]
    symbol: Annotated[str, Field(...)]
    side: Annotated[PositionSide, Field(...)]
    quantity: Annotated[Decimal, Field(...)]
    entry_price: Annotated[Decimal, Field(...)]
    exit_price: Annotated[Decimal, Field(...)]
    stop_loss: Annotated[Decimal, Field(...)]
    take_profit: Annotated[Decimal | None, Field()] = None
    pnl_usdt: Annotated[Decimal, Field(...)]
    close_reason: Annotated[str, Field(...)]
    leverage: Annotated[int, Field(..., ge=1)]
    opened_at_ms: Annotated[int, Field(..., ge=0)]

    model_config = UI_MODEL_CONFIG


class UiCandlesEventSchema(BaseModel):
    """Closed candles for one symbol: a startup backfill batch or a single close."""

    type: Annotated[Literal["candles"], Field()] = "candles"
    ts_ms: Annotated[int, Field(..., ge=0)]
    symbol: Annotated[str, Field(...)]
    interval: Annotated[str, Field(..., min_length=1)]
    candles: Annotated[list[UiCandleSchema], Field(..., min_length=1)]

    model_config = UI_MODEL_CONFIG


class UiTrendDaySchema(BaseModel):
    day_ms: Annotated[int, Field(..., ge=0)]
    close: Annotated[float, Field(...)]
    upper: Annotated[float | None, Field()] = None
    lower: Annotated[float | None, Field()] = None
    exit: Annotated[float | None, Field()] = None
    signal: Annotated[float, Field(...)]

    model_config = UI_MODEL_CONFIG


class UiVolSpikeRuleSchema(BaseModel):
    history_hours: Annotated[int, Field(..., ge=1)]
    min_history_hours: Annotated[int, Field(..., ge=1)]
    quantile: Annotated[float, Field(...)]
    scale: Annotated[float, Field(...)]

    model_config = UI_MODEL_CONFIG


class UiVolSpikeReadingSchema(BaseModel):
    hour_ms: Annotated[int, Field(..., ge=0)]
    rv: Annotated[float, Field(..., ge=0)]
    threshold: Annotated[float | None, Field()] = None

    model_config = UI_MODEL_CONFIG


class UiTrendHalvingSchema(BaseModel):
    hour_ms: Annotated[int, Field(..., ge=0)]
    rv: Annotated[float, Field(..., ge=0)]
    threshold: Annotated[float, Field(..., ge=0)]
    target_weight: Annotated[float, Field(..., ge=0)]

    model_config = UI_MODEL_CONFIG


class UiTrendSymbolSchema(BaseModel):
    symbol: Annotated[str, Field(...)]
    signal: Annotated[float, Field(...)]
    close: Annotated[float, Field(...)]
    entry_level: Annotated[float, Field(...)]
    exit_level: Annotated[float, Field(...)]
    annual_vol: Annotated[float | None, Field()] = None
    target_weight: Annotated[float, Field(...)]
    held_weight: Annotated[float, Field(...)]
    # Latest closed hour of a held symbol, and today's halving if one fired.
    spike: Annotated[UiVolSpikeReadingSchema | None, Field()] = None
    halving: Annotated[UiTrendHalvingSchema | None, Field()] = None
    days: Annotated[list[UiTrendDaySchema], Field(...)]

    model_config = UI_MODEL_CONFIG


class UiTrendStateEventSchema(BaseModel):
    """The trend rule's full per-symbol state; each one replaces the last."""

    type: Annotated[Literal["trend_state"], Field()] = "trend_state"
    ts_ms: Annotated[int, Field(..., ge=0)]
    day: Annotated[date, Field(...)]
    lookback: Annotated[int, Field(..., ge=1)]
    exit_rule: Annotated[Literal["low", "mid"], Field(...)]
    next_rebalance_ms: Annotated[int, Field(..., ge=0)]
    symbols: Annotated[list[UiTrendSymbolSchema], Field(...)]
    annual_vol_target: Annotated[float, Field(...)]
    max_leverage: Annotated[float, Field(...)]
    vol_window: Annotated[int, Field(...)]
    buffer_band: Annotated[float, Field(...)]
    disaster_stop_pct: Annotated[float, Field(...)]
    # None when vol-spike halving is off.
    vol_spike: Annotated[UiVolSpikeRuleSchema | None, Field()] = None

    model_config = UI_MODEL_CONFIG


type UiEvent = Annotated[
    UiAccountEventSchema
    | UiDecisionEventSchema
    | UiTradeEventSchema
    | UiPositionClosedEventSchema
    | UiCandlesEventSchema
    | UiTrendStateEventSchema,
    Field(discriminator="type"),
]

UI_EVENT_ADAPTER: TypeAdapter[UiEvent] = TypeAdapter(UiEvent)
