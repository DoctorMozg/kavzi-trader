"""
Market data models for SQLAlchemy.

This module defines SQLAlchemy models for market data and related entities.
These models map to the database tables for storing market data and features.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
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

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    interval: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
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
        UniqueConstraint(
            "symbol",
            "interval",
            "timestamp",
            name="uix_market_data_symbol_interval_timestamp",
        ),
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


class FeatureModel(BaseModel):
    """
    SQLAlchemy model for features table.

    Stores calculated features for market data points.
    """

    __tablename__ = "features"

    market_data_id: Mapped[int] = mapped_column(
        ForeignKey("market_data.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_value: Mapped[Decimal] = mapped_column(NUMERIC(24, 8), nullable=False)

    # Relationships
    market_data: Mapped["MarketDataModel"] = relationship(
        "MarketDataModel",
        back_populates="features",
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "market_data_id",
            "feature_name",
            name="uix_feature_market_data_id_feature_name",
        ),
        Index(
            "ix_feature_market_data_id_feature_name",
            "market_data_id",
            "feature_name",
        ),
    )

    @classmethod
    def create_batch(
        cls,
        market_data_id: int,
        features: dict[str, float],
    ) -> list["FeatureModel"]:
        """
        Create multiple feature models from a dictionary.

        Args:
            market_data_id: ID of the market data record
            features: Dictionary of feature name -> value

        Returns:
            List of feature model instances
        """
        return [
            cls(market_data_id=market_data_id, feature_name=name, feature_value=value)
            for name, value in features.items()
        ]
