"""Messages the UI server sends to browsers over the WebSocket."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from kavzi_trader.ui.event_schemas import (
    UI_MODEL_CONFIG,
    UiAccountEventSchema,
    UiCandleSchema,
    UiDecisionEventSchema,
    UiEvent,
    UiPositionClosedEventSchema,
    UiTradeEventSchema,
)


class UiSnapshotSchema(BaseModel):
    """Full dashboard state; lists are oldest-first and bounded by UiConfigSchema."""

    account: Annotated[UiAccountEventSchema | None, Field()] = None
    decisions: Annotated[list[UiDecisionEventSchema], Field()] = Field(
        default_factory=list
    )
    trades: Annotated[list[UiTradeEventSchema], Field()] = Field(default_factory=list)
    closed_positions: Annotated[list[UiPositionClosedEventSchema], Field()] = Field(
        default_factory=list
    )
    candles: Annotated[dict[str, list[UiCandleSchema]], Field()] = Field(
        default_factory=dict
    )
    candle_interval: Annotated[str | None, Field()] = None

    model_config = UI_MODEL_CONFIG


class UiSnapshotMessageSchema(BaseModel):
    type: Annotated[Literal["snapshot"], Field()] = "snapshot"
    seq: Annotated[int, Field(..., ge=0)]
    snapshot: Annotated[UiSnapshotSchema, Field(...)]

    model_config = UI_MODEL_CONFIG


class UiEventMessageSchema(BaseModel):
    """A delta; seq is consecutive after the snapshot's seq for one connection."""

    type: Annotated[Literal["event"], Field()] = "event"
    seq: Annotated[int, Field(..., ge=1)]
    event: Annotated[UiEvent, Field(...)]

    model_config = UI_MODEL_CONFIG


type UiServerMessage = Annotated[
    UiSnapshotMessageSchema | UiEventMessageSchema,
    Field(discriminator="type"),
]

UI_SERVER_MESSAGE_ADAPTER: TypeAdapter[UiServerMessage] = TypeAdapter(UiServerMessage)
