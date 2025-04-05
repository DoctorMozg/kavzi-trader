"""
Market data models for SQLAlchemy.

This module defines SQLAlchemy models for market data and related entities.
These models map to the database tables for storing market data and features.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import NUMERIC
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.storage.models.base import BaseModel


class MarketDataModel(BaseModel):
    """
    SQLAlchemy model for market_data table.

    Stores historical market data (candlesticks) for trading pairs.
    """

    __tablename__ = "market_data"

    # Keep the composite primary key
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
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

    # Relationships
    features: Mapped[list["FeatureModel"]] = relationship(
        "FeatureModel",
        back_populates="market_data",
        cascade="all, delete-orphan",
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
        DateTime,
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
    trade_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)

    # Additional id field for internal use
    id: Mapped[int] = mapped_column(
        Integer,
        autoincrement=True,
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


class FeatureModel(BaseModel):
    """
    SQLAlchemy model for features table.

    Stores calculated features for market data points.
    """

    __tablename__ = "features"

    # Link to market_data via timestamp, symbol, interval
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        primary_key=True,
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        nullable=False,
    )
    interval: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
        nullable=False,
    )
    feature_name: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        nullable=False,
    )
    feature_value: Mapped[Decimal] = mapped_column(NUMERIC(24, 8), nullable=False)

    # Relationships
    market_data: Mapped["MarketDataModel"] = relationship(
        "MarketDataModel",
        back_populates="features",
        primaryjoin="and_(FeatureModel.timestamp==MarketDataModel.timestamp, "
        "FeatureModel.symbol==MarketDataModel.symbol, "
        "FeatureModel.interval==MarketDataModel.interval)",
    )

    # Constraints
    __table_args__ = (
        # Foreign key constraint at the table level
        ForeignKeyConstraint(
            ["timestamp", "symbol", "interval"],
            ["market_data.timestamp", "market_data.symbol", "market_data.interval"],
            ondelete="CASCADE",
            name="fk_features_market_data",
        ),
        Index(
            "ix_feature_market_data_feature_name",
            "timestamp",
            "symbol",
            "interval",
            "feature_name",
        ),
    )

    @classmethod
    def create_batch(
        cls,
        timestamp: datetime,
        symbol: str,
        interval: str,
        features: dict[str, float],
    ) -> list["FeatureModel"]:
        """
        Create multiple feature models from a dictionary.

        Args:
            timestamp: Timestamp of the market data point
            symbol: Trading pair symbol
            interval: Kline interval
            features: Dictionary of feature name -> value

        Returns:
            List of feature model instances
        """
        return [
            cls(
                timestamp=timestamp,
                symbol=symbol,
                interval=interval,
                feature_name=name,
                feature_value=value,
            )
            for name, value in features.items()
        ]
