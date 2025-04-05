"""
Market data models for SQLAlchemy.

This module defines SQLAlchemy models for market data and related entities.
These models map to the database tables for storing market data and features.
"""

from datetime import datetime
from decimal import Decimal

from pyparsing import Any
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import NUMERIC
from sqlalchemy.orm import Mapped, mapped_column

from src.data.storage.models.base import BaseModel


class MarketDataModel(BaseModel):
    """
    SQLAlchemy model for market_data table.

    Stores historical market data (candlesticks) for trading pairs.
    """

    __tablename__ = "market_data"

    # Keep the composite primary key
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        nullable=False,
        index=True,
    )
    interval: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
        nullable=False,
        index=True,
    )

    opened: Mapped[Decimal] = mapped_column(NUMERIC(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(NUMERIC(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(NUMERIC(18, 8), nullable=False)
    closed: Mapped[Decimal] = mapped_column(NUMERIC(18, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(NUMERIC(24, 8), nullable=False)
    quote_volume: Mapped[Decimal | None] = mapped_column(NUMERIC(24, 8), nullable=True)
    trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taker_buy_base_volume: Mapped[Decimal | None] = mapped_column(
        NUMERIC(24, 8),
        nullable=True,
    )
    taker_buy_quote_volume: Mapped[Decimal | None] = mapped_column(
        NUMERIC(24, 8),
        nullable=True,
    )
    features_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
    )

    # Constraints
    __table_args__ = (
        Index(
            "ix_market_data_symbol_interval_timestamp",
            "symbol",
            "interval",
            "timestamp",
        ),
    )

    @property
    def price_range(self) -> float:
        """Calculate the price range (high - low)."""
        return float(self.high - self.low)

    @property
    def price_change(self) -> float:
        """Calculate the price change (close - open)."""
        return float(self.closed - self.opened)

    @property
    def price_change_percent(self) -> float:
        """Calculate the price change percentage."""
        if float(self.opened) == 0:
            return 0.0
        return (float(self.closed) - float(self.opened)) / float(self.opened) * 100.0


class TradeDataModel(BaseModel):
    """
    SQLAlchemy model for trade_data table.

    Stores historical trade data for trading pairs.
    """

    __tablename__ = "trade_data"

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        nullable=False,
        index=True,
    )

    price: Mapped[Decimal] = mapped_column(NUMERIC(18, 8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(NUMERIC(24, 8), nullable=False)
    quote_quantity: Mapped[Decimal] = mapped_column(NUMERIC(24, 8), nullable=False)
    is_buyer_maker: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_best_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    buyer_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seller_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Constraints
    __table_args__ = (
        Index(
            "ix_trade_data_symbol_timestamp",
            "symbol",
            "timestamp",
        ),
    )
