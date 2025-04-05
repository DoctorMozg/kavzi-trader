"""
Portfolio-related database models for SQLAlchemy.

This module defines SQLAlchemy models for portfolio management.
These models map to the database tables for storing portfolio and asset data.
"""

from decimal import Decimal
from typing import cast

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kavzi_trader.data.storage.models.base import BaseModel


class PortfolioModel(BaseModel):
    """
    SQLAlchemy model for portfolios table.

    Stores portfolio metadata and balances.
    """

    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    is_paper_trading: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # Relationships
    assets: Mapped[list["PortfolioAssetModel"]] = relationship(
        "PortfolioAssetModel",
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )

    @property
    def total_value(self) -> float:
        """
        Calculate the total portfolio value including all assets.

        Returns:
            Total portfolio value in base currency
        """
        asset_values = sum(
            float(asset.quantity) * float(asset.current_price) for asset in self.assets
        )
        return float(self.current_balance) + asset_values

    @property
    def profit_loss(self) -> float:
        """
        Calculate the total profit/loss for the portfolio.

        Returns:
            Total profit/loss in base currency
        """
        return self.total_value - float(self.initial_balance)

    @property
    def profit_loss_percentage(self) -> float:
        """
        Calculate the profit/loss percentage for the portfolio.

        Returns:
            Profit/loss as a percentage
        """
        if float(self.initial_balance) == 0:
            return 0.0
        return (self.profit_loss / float(self.initial_balance)) * 100.0

    def get_asset(self, symbol: str) -> "PortfolioAssetModel | None":
        """
        Get a specific asset from the portfolio.

        Args:
            symbol: Asset symbol to retrieve

        Returns:
            PortfolioAssetModel or None if not found
        """
        for asset in self.assets:
            if asset.asset == symbol:
                return cast(PortfolioAssetModel, asset)
        return None


class PortfolioAssetModel(BaseModel):
    """
    SQLAlchemy model for portfolio_assets table.

    Stores information about assets held in portfolios.
    """

    __tablename__ = "portfolio_assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    average_buy_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)

    # Relationships
    portfolio: Mapped["PortfolioModel"] = relationship(
        "PortfolioModel",
        back_populates="assets",
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "asset",
            name="uix_portfolio_asset_portfolio_id_asset",
        ),
        Index("ix_portfolio_asset_portfolio_id_asset", "portfolio_id", "asset"),
    )

    @property
    def current_value(self) -> float:
        """
        Calculate the current value of the asset.

        Returns:
            Current value in base currency
        """
        return float(self.quantity) * float(self.current_price)

    @property
    def cost_basis(self) -> float:
        """
        Calculate the cost basis of the asset.

        Returns:
            Cost basis in base currency
        """
        return float(self.quantity) * float(self.average_buy_price)

    @property
    def profit_loss(self) -> float:
        """
        Calculate the profit/loss for this asset.

        Returns:
            Profit/loss in base currency
        """
        return self.current_value - self.cost_basis

    @property
    def profit_loss_percentage(self) -> float:
        """
        Calculate the profit/loss percentage for this asset.

        Returns:
            Profit/loss as a percentage
        """
        if self.cost_basis == 0:
            return 0.0
        return (self.profit_loss / self.cost_basis) * 100.0

    def update_quantity(self, delta_quantity: float, price: float) -> None:
        """
        Update the asset quantity and average buy price.

        Args:
            delta_quantity: Change in quantity (positive for buy, negative for sell)
            price: Price of the transaction
        """
        if delta_quantity > 0:
            # Buying more - update average price
            total_cost = self.cost_basis + (delta_quantity * price)
            total_quantity = float(self.quantity) + delta_quantity
            self.average_buy_price = (
                total_cost / total_quantity if total_quantity > 0 else 0
            )

        # Update quantity
        self.quantity = float(self.quantity) + delta_quantity

    def update_current_price(self, price: float) -> None:
        """
        Update the current price of the asset.

        Args:
            price: New current price
        """
        self.current_price = price
