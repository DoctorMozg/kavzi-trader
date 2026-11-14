"""
Data models for API responses.

This module defines common data models for representing API responses.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


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
