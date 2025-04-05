"""
SQLAlchemy database models for KavziTrader.

This module exports all SQLAlchemy model classes for use throughout the application.
"""

# Base models
from kavzi_trader.data.storage.models.base import BaseModel

# Market data models
from kavzi_trader.data.storage.models.market_data import (
    MarketDataModel,
    TradeDataModel,
)

# Portfolio models
from kavzi_trader.data.storage.models.portfolio import PortfolioAssetModel, PortfolioModel

# System models
from kavzi_trader.data.storage.models.system import SystemLogModel

# Trading models
from kavzi_trader.data.storage.models.trading import (
    PerformanceModel,
    StrategyModel,
    TradeModel,
    TradingPlanModel,
)

# Export all models for easy importing
__all__ = [
    # Base models
    "BaseModel",
    # Market data models (Time-series)
    "MarketDataModel",
    "TradeDataModel",
    # Portfolio models
    "PortfolioModel",
    "PortfolioAssetModel",
    # System models
    "SystemLogModel",
    # Trading models
    "StrategyModel",
    "TradingPlanModel",
    "TradeModel",
    "PerformanceModel",
]
