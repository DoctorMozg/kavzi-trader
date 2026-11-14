"""Events the trader publishes to the dashboard; this is the UI wire contract."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PositionSide = Literal["LONG", "SHORT"]
DecisionStage = Literal["scout", "analyst", "trader", "filter", "position"]


class UiOpenPositionSchema(BaseModel):
    id: Annotated[str, Field(...)]
    symbol: Annotated[str, Field(...)]
    side: Annotated[PositionSide, Field(...)]
    quantity: Annotated[Decimal, Field(...)]
    entry_price: Annotated[Decimal, Field(...)]
    mark_price: Annotated[Decimal, Field(...)]
    stop_loss: Annotated[Decimal, Field(...)]
    take_profit: Annotated[Decimal, Field(...)]
    unrealized_pnl_usdt: Annotated[Decimal, Field(...)]
    leverage: Annotated[int, Field(..., ge=1)]
    opened_at_ms: Annotated[int, Field(..., ge=0)]

    model_config = ConfigDict(frozen=True)


class UiCandleSchema(BaseModel):
    open_time_ms: Annotated[int, Field(..., ge=0)]
    open: Annotated[Decimal, Field(...)]
    high: Annotated[Decimal, Field(...)]
    low: Annotated[Decimal, Field(...)]
    close: Annotated[Decimal, Field(...)]
    volume: Annotated[Decimal, Field(...)]

    model_config = ConfigDict(frozen=True)


class UiAccountEventSchema(BaseModel):
    """Periodic full account state; session fields repeat so trimming is safe."""

    type: Annotated[Literal["account"], Field(default="account")]
    ts_ms: Annotated[int, Field(..., ge=0)]
    session_started_at_ms: Annotated[int, Field(..., ge=0)]
    is_paper: Annotated[bool, Field(...)]
    initial_balance_usdt: Annotated[Decimal, Field(...)]
    balance_usdt: Annotated[Decimal, Field(...)]
    unrealized_pnl_usdt: Annotated[Decimal, Field(...)]
    positions: Annotated[list[UiOpenPositionSchema], Field(default_factory=list)]
    prices: Annotated[dict[str, Decimal], Field(default_factory=dict)]
    running_loops: Annotated[list[str], Field(default_factory=list)]

    model_config = ConfigDict(frozen=True)


class UiDecisionEventSchema(BaseModel):
    """One step of the Scout -> Analyst -> Trader pipeline or a position action."""

    type: Annotated[Literal["decision"], Field(default="decision")]
    ts_ms: Annotated[int, Field(..., ge=0)]
    symbol: Annotated[str, Field(...)]
    stage: Annotated[DecisionStage, Field(...)]
    verdict: Annotated[str, Field(..., min_length=1)]
    summary: Annotated[str, Field(...)]
    reasoning: Annotated[str | None, Field(default=None)]
    confidence: Annotated[float | None, Field(default=None, ge=0.0, le=1.0)]
    latency_ms: Annotated[int | None, Field(default=None, ge=0)]

    model_config = ConfigDict(frozen=True)


class UiTradeEventSchema(BaseModel):
    type: Annotated[Literal["trade"], Field(default="trade")]
    ts_ms: Annotated[int, Field(..., ge=0)]
    symbol: Annotated[str, Field(...)]
    side: Annotated[Literal["LONG", "SHORT", "CLOSE"], Field(...)]
    status: Annotated[str, Field(...)]
    confidence: Annotated[float, Field(..., ge=0.0, le=1.0)]
    entry_price: Annotated[Decimal | None, Field(default=None)]
    quantity: Annotated[Decimal | None, Field(default=None)]
    stop_loss: Annotated[Decimal | None, Field(default=None)]
    take_profit: Annotated[Decimal | None, Field(default=None)]
    reasoning: Annotated[str, Field(default="")]

    model_config = ConfigDict(frozen=True)


class UiPositionClosedEventSchema(BaseModel):
    type: Annotated[Literal["position_closed"], Field(default="position_closed")]
    ts_ms: Annotated[int, Field(..., ge=0)]
    symbol: Annotated[str, Field(...)]
    side: Annotated[PositionSide, Field(...)]
    quantity: Annotated[Decimal, Field(...)]
    entry_price: Annotated[Decimal, Field(...)]
    exit_price: Annotated[Decimal, Field(...)]
    stop_loss: Annotated[Decimal, Field(...)]
    take_profit: Annotated[Decimal, Field(...)]
    pnl_usdt: Annotated[Decimal, Field(...)]
    close_reason: Annotated[str, Field(...)]
    leverage: Annotated[int, Field(..., ge=1)]
    opened_at_ms: Annotated[int, Field(..., ge=0)]

    model_config = ConfigDict(frozen=True)


class UiCandlesEventSchema(BaseModel):
    """Closed candles for one symbol: a startup backfill batch or a single close."""

    type: Annotated[Literal["candles"], Field(default="candles")]
    ts_ms: Annotated[int, Field(..., ge=0)]
    symbol: Annotated[str, Field(...)]
    interval: Annotated[str, Field(..., min_length=1)]
    candles: Annotated[list[UiCandleSchema], Field(..., min_length=1)]

    model_config = ConfigDict(frozen=True)


type UiEvent = Annotated[
    UiAccountEventSchema
    | UiDecisionEventSchema
    | UiTradeEventSchema
    | UiPositionClosedEventSchema
    | UiCandlesEventSchema,
    Field(discriminator="type"),
]

UI_EVENT_ADAPTER: TypeAdapter[UiEvent] = TypeAdapter(UiEvent)
