"""Events the trader publishes to the dashboard; this is the UI wire contract."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PositionSide = Literal["LONG", "SHORT"]
DecisionStage = Literal["scout", "analyst", "trader", "filter", "position"]

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
    confidence: Annotated[float, Field(..., ge=0.0, le=1.0)]
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


type UiEvent = Annotated[
    UiAccountEventSchema
    | UiDecisionEventSchema
    | UiTradeEventSchema
    | UiPositionClosedEventSchema
    | UiCandlesEventSchema,
    Field(discriminator="type"),
]

UI_EVENT_ADAPTER: TypeAdapter[UiEvent] = TypeAdapter(UiEvent)
