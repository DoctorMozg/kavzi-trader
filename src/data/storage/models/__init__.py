"""
SQLAlchemy database models for KavziTrader.

This module exports all SQLAlchemy model classes for use throughout the application.
"""

# Base models
from src.data.storage.models.base import BaseModel

# Market data models
from src.data.storage.models.market_data import FeatureModel, MarketDataModel

# Model-related models
from src.data.storage.models.model import ModelModel, ModelTrainingRunModel

# Portfolio models
from src.data.storage.models.portfolio import PortfolioAssetModel, PortfolioModel

# System models
from src.data.storage.models.system import SystemConfigModel, SystemLogModel

# Trading-related models
from src.data.storage.models.trading import (
    PerformanceModel,
    StrategyModel,
    TradeModel,
    TradingPlanModel,
)

# Export all models for easy importing
__all__ = [
    # Base models
    "BaseModel",
    # Market data models
    "MarketDataModel",
    "FeatureModel",
    # Model-related models
    "ModelModel",
    "ModelTrainingRunModel",
    # Trading-related models
    "StrategyModel",
    "TradingPlanModel",
    "TradeModel",
    "PerformanceModel",
    # Portfolio models
    "PortfolioModel",
    "PortfolioAssetModel",
    # System models
    "SystemLogModel",
    "SystemConfigModel",
]
