"""
Database storage module for KavziTrader.

This module provides database functionality for storing and retrieving
market data, models, trading information, and system configuration.
"""

from src.data.storage.database import (
    Base,
    Database,
    create_database_url,
    create_db_engine,
    initialize_database,
)

# Re-export SQLAlchemy models
from src.data.storage.models import (
    BaseModel,
    FeatureModel,
    MarketDataModel,
    ModelModel,
    ModelTrainingRunModel,
    PerformanceModel,
    PortfolioAssetModel,
    PortfolioModel,
    StrategyModel,
    SystemConfigModel,
    SystemLogModel,
    TradeModel,
    TradingPlanModel,
)

__all__ = [
    # Database connection
    "Base",
    "Database",
    "create_database_url",
    "create_db_engine",
    "initialize_database",
    "get_db",
    # SQLAlchemy models
    "BaseModel",
    "MarketDataModel",
    "FeatureModel",
    "ModelModel",
    "ModelTrainingRunModel",
    "StrategyModel",
    "TradingPlanModel",
    "TradeModel",
    "PerformanceModel",
    "PortfolioModel",
    "PortfolioAssetModel",
    "SystemLogModel",
    "SystemConfigModel",
]
