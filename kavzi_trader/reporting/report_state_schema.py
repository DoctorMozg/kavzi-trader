from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportActionEntrySchema(BaseModel):
    """Single entry in the general activity log."""

    timestamp: Annotated[datetime, Field(...)]
    action_type: Annotated[str, Field(...)]
    symbol: Annotated[str, Field(...)]
    summary: Annotated[str, Field(...)]
    details: Annotated[str | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)


class ReportTradeEntrySchema(BaseModel):
    """Entry in the buy/sell trade list."""

    timestamp: Annotated[datetime, Field(...)]
    symbol: Annotated[str, Field(...)]
    side: Annotated[Literal["LONG", "SHORT", "CLOSE"], Field(...)]
    entry_price: Annotated[Decimal | None, Field(default=None)]
    quantity: Annotated[Decimal | None, Field(default=None)]
    stop_loss: Annotated[Decimal | None, Field(default=None)]
    take_profit: Annotated[Decimal | None, Field(default=None)]
    status: Annotated[str, Field(...)]
    confidence: Annotated[float, Field(..., ge=0.0, le=1.0)]
    reasoning: Annotated[str, Field(default="")]

    model_config = ConfigDict(frozen=True)


class ReportPositionEntrySchema(BaseModel):
    """Snapshot of a single open position for the report."""

    symbol: Annotated[str, Field(...)]
    side: Annotated[Literal["LONG", "SHORT"], Field(...)]
    quantity: Annotated[Decimal, Field(...)]
    entry_price: Annotated[Decimal, Field(...)]
    current_price: Annotated[Decimal, Field(...)]
    stop_loss: Annotated[Decimal, Field(...)]
    take_profit: Annotated[Decimal, Field(...)]
    unrealized_pnl: Annotated[Decimal, Field(...)]
    leverage: Annotated[int, Field(...)]
    opened_at: Annotated[datetime, Field(...)]

    model_config = ConfigDict(frozen=True)


class ReportClosedPositionEntrySchema(BaseModel):
    """Record of a closed position with realized PnL."""

    symbol: Annotated[str, Field(...)]
    side: Annotated[Literal["LONG", "SHORT"], Field(...)]
    quantity: Annotated[Decimal, Field(...)]
    entry_price: Annotated[Decimal, Field(...)]
    exit_price: Annotated[Decimal, Field(...)]
    stop_loss: Annotated[Decimal, Field(...)]
    take_profit: Annotated[Decimal, Field(...)]
    pnl: Annotated[Decimal, Field(...)]
    close_reason: Annotated[str, Field(...)]
    leverage: Annotated[int, Field(...)]
    opened_at: Annotated[datetime, Field(...)]
    closed_at: Annotated[datetime, Field(...)]

    model_config = ConfigDict(frozen=True)


class ReportMarketPriceSchema(BaseModel):
    """Current price for a single trading pair."""

    symbol: Annotated[str, Field(...)]
    price: Annotated[Decimal, Field(...)]

    model_config = ConfigDict(frozen=True)


class ReportStateSchema(BaseModel):
    """Complete report state rendered to HTML."""

    session_started_at: Annotated[datetime, Field(...)]
    last_updated_at: Annotated[datetime, Field(...)]
    version: Annotated[int, Field(default=1, ge=1)]

    initial_balance_usdt: Annotated[Decimal, Field(...)]
    current_balance_usdt: Annotated[Decimal, Field(...)]
    session_revenue_usdt: Annotated[Decimal, Field(default=Decimal(0))]
    unrealized_pnl_usdt: Annotated[Decimal, Field(default=Decimal(0))]

    active_positions_count: Annotated[int, Field(default=0, ge=0)]

    open_positions: Annotated[
        list[ReportPositionEntrySchema],
        Field(default_factory=list),
    ]
    closed_positions: Annotated[
        list[ReportClosedPositionEntrySchema],
        Field(default_factory=list),
    ]
    market_prices: Annotated[
        list[ReportMarketPriceSchema],
        Field(default_factory=list),
    ]

    actions: Annotated[
        list[ReportActionEntrySchema],
        Field(default_factory=list),
    ]
    trades: Annotated[
        list[ReportTradeEntrySchema],
        Field(default_factory=list),
    ]

    model_config = ConfigDict(frozen=True)
