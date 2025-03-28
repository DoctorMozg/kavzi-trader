"""
Trading-related database models for SQLAlchemy.

This module defines SQLAlchemy models for trading entities.
These models map to the database tables for storing strategies, trading plans,
and trades.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, cast

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.storage.models.base import BaseModel


class StrategyModel(BaseModel):
    """
    SQLAlchemy model for strategies table.

    Stores trading strategies metadata and parameters.
    """

    __tablename__ = "strategies"

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    # Relationships
    model: Mapped[Optional["ModelModel"]] = relationship(
        "ModelModel",
        back_populates="strategies",
    )
    trading_plans: Mapped[list["TradingPlanModel"]] = relationship(
        "TradingPlanModel",
        back_populates="strategy",
        cascade="all, delete-orphan",
    )
    trades: Mapped[list["TradeModel"]] = relationship(
        "TradeModel",
        back_populates="strategy",
    )
    performance_metrics: Mapped[list["PerformanceModel"]] = relationship(
        "PerformanceModel",
        back_populates="strategy",
    )

    def activate(self) -> None:
        """Activate this strategy."""
        self.is_active = True

    def deactivate(self) -> None:
        """Deactivate this strategy."""
        self.is_active = False


class TradingPlanModel(BaseModel):
    """
    SQLAlchemy model for trading_plans table.

    Stores trading plan configurations.
    """

    __tablename__ = "trading_plans"

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    risk_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    entry_conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    exit_conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schedule: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    symbols: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    # Relationships
    strategy: Mapped["StrategyModel"] = relationship(
        "StrategyModel",
        back_populates="trading_plans",
    )
    trades: Mapped[list["TradeModel"]] = relationship(
        "TradeModel",
        back_populates="plan",
    )
    performance_metrics: Mapped[list["PerformanceModel"]] = relationship(
        "PerformanceModel",
        back_populates="plan",
    )

    def activate(self) -> None:
        """Activate this trading plan."""
        self.is_active = True

    def deactivate(self) -> None:
        """Deactivate this trading plan."""
        self.is_active = False

    def get_symbols(self) -> list[str]:
        """
        Get the list of symbols for this trading plan.

        Returns:
            List of trading pair symbols
        """
        if isinstance(self.symbols, list):
            return self.symbols
        if isinstance(self.symbols, dict) and "symbols" in self.symbols:
            return cast(list[str], self.symbols["symbols"])
        return []


class TradeModel(BaseModel):
    """
    SQLAlchemy model for trades table.

    Stores individual trade records.
    """

    __tablename__ = "trades"

    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("trading_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY or SELL
    order_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # MARKET, LIMIT, etc.
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    executed_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    profit_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    profit_loss_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )
    commission: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entry_time: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )
    exit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_paper_trading: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)

    # Relationships
    strategy: Mapped["StrategyModel"] = relationship(
        "StrategyModel",
        back_populates="trades",
    )
    plan: Mapped["TradingPlanModel"] = relationship(
        "TradingPlanModel",
        back_populates="trades",
    )

    # Constraints
    __table_args__ = (Index("ix_trade_symbol_entry_time", "symbol", "entry_time"),)

    @property
    def is_completed(self) -> bool:
        """Check if the trade is completed."""
        return self.status in ["FILLED", "CANCELLED", "REJECTED"]

    @property
    def is_successful(self) -> bool:
        """Check if the trade was successful."""
        if self.profit_loss is None:
            return False
        return float(self.profit_loss) > 0

    @property
    def duration_seconds(self) -> float | None:
        """
        Calculate the duration of the trade in seconds.

        Returns:
            Duration in seconds or None if exit_time or entry_time is not set
        """
        if self.exit_time is None or self.entry_time is None:
            return None

        return cast(float, (self.exit_time - self.entry_time).total_seconds())


class PerformanceModel(BaseModel):
    """
    SQLAlchemy model for performance table.

    Stores performance metrics for strategies and trading plans.
    """

    __tablename__ = "performance"

    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("trading_plans.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    profit_loss: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    profit_loss_percentage: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
    )
    max_drawdown: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    average_profit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )
    average_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    recovery_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    # Relationships
    strategy: Mapped["StrategyModel"] = relationship(
        "StrategyModel",
        back_populates="performance_metrics",
    )
    plan: Mapped[Optional["TradingPlanModel"]] = relationship(
        "TradingPlanModel",
        back_populates="performance_metrics",
    )

    # Constraints
    __table_args__ = (
        Index(
            "ix_performance_strategy_id_start_time_end_time",
            "strategy_id",
            "start_time",
            "end_time",
        ),
    )

    @classmethod
    def calculate_from_trades(
        cls,
        strategy_id: int,
        start_time: datetime,
        end_time: datetime,
        trades: list[TradeModel],
        plan_id: int | None = None,
    ) -> "PerformanceModel":
        """
        Calculate performance metrics from a list of trades.

        Args:
            strategy_id: ID of the strategy
            start_time: Start time of the period
            end_time: End time of the period
            trades: List of trades to analyze
            plan_id: Optional ID of the trading plan

        Returns:
            PerformanceModel instance with calculated metrics
        """
        # Initialize metrics
        total_trades = len(trades)
        winning_trades = sum(1 for trade in trades if trade.is_successful)
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # Calculate profit/loss
        total_profit_loss = sum(
            float(trade.profit_loss if trade.profit_loss is not None else 0)
            for trade in trades
        )

        # Calculate drawdown and other metrics
        # This is a simplified version - full implementation would have more complex calculations
        max_drawdown = 0  # Placeholder
        sharpe_ratio = None  # Placeholder
        average_profit = None
        average_loss = None
        profit_factor = None
        recovery_factor = None

        if winning_trades > 0:
            average_profit = (
                sum(
                    float(trade.profit_loss if trade.profit_loss is not None else 0)
                    for trade in trades
                    if trade.is_successful
                )
                / winning_trades
            )

        if losing_trades > 0:
            average_loss = (
                sum(
                    float(trade.profit_loss if trade.profit_loss is not None else 0)
                    for trade in trades
                    if not trade.is_successful
                )
                / losing_trades
            )

        if (
            average_loss is not None
            and average_loss != 0
            and average_profit is not None
        ):
            profit_factor = (
                abs(average_profit / average_loss) if average_loss != 0 else None
            )

        # Create and return the performance model
        return cls(
            strategy_id=strategy_id,
            plan_id=plan_id,
            start_time=start_time,
            end_time=end_time,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_loss=total_profit_loss,
            profit_loss_percentage=0,  # Placeholder
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            average_profit=average_profit,
            average_loss=average_loss,
            profit_factor=profit_factor,
            recovery_factor=recovery_factor,
        )
