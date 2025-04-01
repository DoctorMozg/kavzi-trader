"""
Utility functions for working with TimescaleDB hypertables.

This module provides helper functions for setting up and managing
TimescaleDB hypertables for time-series data.
"""

import logging
from typing import Sequence, Type

from sqlalchemy.orm import DeclarativeBase

from src.data.storage.database_async import AsyncDatabase

logger = logging.getLogger(__name__)


async def setup_hypertable(
    db: AsyncDatabase,
    model: Type[DeclarativeBase],
    time_column: str = "created_at",
    chunk_interval: str = "1 day",
    compress_after: str = "7 days",
    retention_period: str = "365 days",
) -> None:
    """
    Set up a TimescaleDB hypertable for a model.

    This function:
    1. Creates a hypertable from the model's table
    2. Adds a compression policy
    3. Adds a retention policy

    Args:
        db: AsyncDatabase instance
        model: SQLAlchemy model class
        time_column: Name of the timestamp column to use as time index
        chunk_interval: Time interval for chunks (e.g., '1 day', '1 hour')
        compress_after: When to compress chunks (e.g., '7 days')
        retention_period: When to drop chunks (e.g., '365 days')
    """
    table_name = model.__tablename__
    
    # Create hypertable
    await db.create_hypertable(
        table_name=table_name,
        time_column_name=time_column,
        chunk_time_interval=chunk_interval,
    )
    
    # Add compression policy
    await db.add_compression_policy(
        table_name=table_name,
        compress_after=compress_after,
    )
    
    # Add retention policy
    await db.add_retention_policy(
        table_name=table_name,
        drop_after=retention_period,
    )
    
    logger.info(
        f"Set up hypertable for {table_name} with compression after {compress_after} "
        f"and retention period of {retention_period}"
    )


async def setup_hypertables(
    db: AsyncDatabase,
    models: Sequence[Type[DeclarativeBase]],
    time_column: str = "created_at",
    chunk_interval: str = "1 day",
    compress_after: str = "7 days",
    retention_period: str = "365 days",
) -> None:
    """
    Set up TimescaleDB hypertables for multiple models.

    Args:
        db: AsyncDatabase instance
        models: Sequence of SQLAlchemy model classes
        time_column: Name of the timestamp column to use as time index
        chunk_interval: Time interval for chunks (e.g., '1 day', '1 hour')
        compress_after: When to compress chunks (e.g., '7 days')
        retention_period: When to drop chunks (e.g., '365 days')
    """
    for model in models:
        await setup_hypertable(
            db=db,
            model=model,
            time_column=time_column,
            chunk_interval=chunk_interval,
            compress_after=compress_after,
            retention_period=retention_period,
        )
    
    logger.info(f"Set up hypertables for {len(models)} models")