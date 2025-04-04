"""
Database storage module for KavziTrader.

This module provides database functionality for storing and retrieving
market data, models, trading information, and system configuration.
"""

from src.data.storage.database_async import (
    AsyncDatabase as Database,
)
from src.data.storage.database_async import (
    Base,
    async_sessionmaker,
    create_database_url,
)
from src.data.storage.database_async import (
    create_async_db_engine as create_db_engine,
)
from src.data.storage.database_async import (
    initialize_async_database as initialize_database,
)

# Re-export SQLAlchemy models
from src.data.storage.models import (
    BaseModel,
    FeatureModel,
    MarketDataModel,
    PortfolioAssetModel,
    PortfolioModel,
    SystemLogModel,
    TradeDataModel,
)

__all__ = [
    # Database connection
    "Base",
    "Database",
    "create_database_url",
    "create_db_engine",
    "initialize_database",
    "get_db",
    "async_sessionmaker",
    # SQLAlchemy models
    "BaseModel",
    "MarketDataModel",
    "FeatureModel",
    "TradeDataModel",
    "PerformanceModel",
    "PortfolioModel",
    "PortfolioAssetModel",
    "SystemLogModel",
    "SystemConfigModel",
]
