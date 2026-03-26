"""
Data models for API responses.

This module defines common data models for representing API responses.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrderSide(StrEnum):
    """Order side enum: BUY or SELL."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Order type enum."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"


class OrderStatus(StrEnum):
    """Order status enum."""

    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    PENDING_CANCEL = "PENDING_CANCEL"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TimeInForce(StrEnum):
    """Time in force enum."""

    GTC = "GTC"  # Good Till Canceled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill


class SymbolInfoSchema(BaseModel):
    """Information about a trading symbol/pair."""

    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    base_precision: int
    quote_precision: int
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal
    min_qty: Decimal
    max_qty: Decimal
    step_size: Decimal
    min_notional: Decimal
    filters: list[dict[str, Any]] | None = None

    model_config = ConfigDict(frozen=True)


class OrderBookEntrySchema(BaseModel):
    """Single entry in the order book (bid or ask)."""

    price: Decimal
    qty: Decimal

    model_config = ConfigDict(frozen=True)


class OrderBookSchema(BaseModel):
    """Order book with bids and asks."""

    bids: list[OrderBookEntrySchema]
    asks: list[OrderBookEntrySchema]
    last_update_id: int | None = None
    timestamp: datetime | None = None

    model_config = ConfigDict(frozen=True)


class TradeSchema(BaseModel):
    """Single trade information."""

    id: int
    price: Decimal
    qty: Decimal
    time: datetime
    is_buyer_maker: bool
    is_best_match: bool = True
    quote_qty: Decimal = Decimal(0)
    first_trade_id: int | None = None
    last_trade_id: int | None = None
    # Optional fields that may be present in some exchanges
    buyer_order_id: int | None = None
    seller_order_id: int | None = None

    model_config = ConfigDict(frozen=True)


class TickerSchema(BaseModel):
    """Ticker information for a symbol."""

    symbol: str
    last_price: Decimal
    price_change: Decimal = Decimal(0)
    price_change_percent: Decimal = Decimal(0)
    weighted_avg_price: Decimal | None = None
    prev_close_price: Decimal | None = None
    last_qty: Decimal | None = None
    bid_price: Decimal | None = None
    bid_qty: Decimal | None = None
    ask_price: Decimal | None = None
    ask_qty: Decimal | None = None
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    volume: Decimal | None = None
    quote_volume: Decimal | None = None
    open_time: datetime | None = None
    close_time: datetime | None = None
    count: int | None = None

    model_config = ConfigDict(frozen=True)


class CandlestickSchema(BaseModel):
    """Candlestick/kline data."""

    open_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    close_time: datetime
    quote_volume: Decimal
    trades_count: int
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal
    interval: str | None = None
    symbol: str | None = None

    model_config = ConfigDict(frozen=True)


class OrderFillSchema(BaseModel):
    """Information about a fill for an order."""

    price: Decimal
    qty: Decimal
    commission: Decimal
    commission_asset: str
    trade_id: int | None = None

    model_config = ConfigDict(frozen=True)


class OrderResponseSchema(BaseModel):
    """Response for order creation or query."""

    symbol: str
    order_id: int
    client_order_id: str
    transact_time: datetime
    price: Decimal
    orig_qty: Decimal
    executed_qty: Decimal
    status: OrderStatus
    time_in_force: TimeInForce
    type: OrderType
    side: OrderSide
    fills: list[OrderFillSchema] = Field(default_factory=list)
    # Optional fields
    stop_price: Decimal | None = None
    iceberg_qty: Decimal | None = None
    time: datetime | None = None
    update_time: datetime | None = None
    is_working: bool | None = None
    orig_quote_order_qty: Decimal | None = None

    model_config = ConfigDict(frozen=True)
