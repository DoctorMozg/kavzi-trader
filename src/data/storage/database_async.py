"""
Database connection and session management for KavziTrader.

This module provides utilities for establishing asynchronous database connections,
managing sessions, and handling transactions with SQLAlchemy.
Includes support for TimescaleDB hypertables for time-series data.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Sequence

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


async def create_database_url(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
) -> URL:
    """
    Create a SQLAlchemy database URL for PostgreSQL.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database username
        password: Database password

    Returns:
        SQLAlchemy URL object
    """
    return URL.create(
        drivername="postgresql+asyncpg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )


async def create_async_db_engine(db_url: URL, echo: bool = False) -> AsyncEngine:
    """
    Create an async SQLAlchemy engine.

    Args:
        db_url: Database URL
        echo: Whether to echo SQL statements

    Returns:
        SQLAlchemy AsyncEngine
    """
    return create_async_engine(
        db_url,
        echo=echo,
        pool_pre_ping=True,  # Check connection before using from pool
        pool_recycle=3600,  # Recycle connections after 1 hour
    )


class AsyncDatabase:
    """
    Async database connection manager for KavziTrader.

    This class provides methods for connecting to the database,
    creating sessions, and executing transactions asynchronously.
    """

    def __init__(self, db_url: URL, echo: bool = False) -> None:
        """
        Initialize the async database connection manager.

        Args:
            db_url: Database URL
            echo: Whether to echo SQL statements
        """
        self.engine = create_async_engine(
            db_url,
            echo=echo,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self.async_session_maker = async_sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            expire_on_commit=False,
        )
        db_url_str = db_url.render_as_string(hide_password=True)
        logger.info(
            f"Async database connection established to {db_url_str}",
        )

    async def create_database_tables(self) -> None:
        """Create all tables defined in SQLAlchemy models."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
        
    async def initialize_timescale_extension(self) -> None:
        """Initialize TimescaleDB extension if it's not already enabled."""
        async with self.session_scope() as session:
            await session.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
            await session.commit()
        logger.info("TimescaleDB extension initialized")
        
    async def create_hypertable(
        self,
        table_name: str,
        time_column_name: str = "created_at",
        chunk_time_interval: str = "1 day",
        if_not_exists: bool = True,
    ) -> None:
        """
        Convert a regular table to a TimescaleDB hypertable.
        
        Args:
            table_name: Name of the table to convert
            time_column_name: Name of the timestamp column to use as time index
            chunk_time_interval: Time interval for chunks (e.g., '1 day', '1 hour')
            if_not_exists: Whether to use IF NOT EXISTS in the SQL
        """
        if_not_exists_clause = "IF NOT EXISTS" if if_not_exists else ""
        
        async with self.session_scope() as session:
            # First ensure TimescaleDB extension is enabled
            await session.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
            
            # Create hypertable
            sql = f"""
            SELECT create_hypertable(
                '{table_name}',
                '{time_column_name}',
                {if_not_exists_clause},
                chunk_time_interval => interval '{chunk_time_interval}'
            );
            """
            await session.execute(sql)
            await session.commit()
            
        logger.info(f"Created hypertable for {table_name} on {time_column_name}")
        
    async def add_compression_policy(
        self,
        table_name: str,
        compress_after: str = "7 days",
        if_not_exists: bool = True,
    ) -> None:
        """
        Add a compression policy to a hypertable.
        
        Args:
            table_name: Name of the hypertable
            compress_after: When to compress chunks (e.g., '7 days')
            if_not_exists: Whether to use IF NOT EXISTS in the SQL
        """
        if_not_exists_clause = "IF NOT EXISTS" if if_not_exists else ""
        
        async with self.session_scope() as session:
            # Enable compression on the table
            await session.execute(f"ALTER TABLE {table_name} SET (timescaledb.compress = true);")
            
            # Add compression policy
            sql = f"""
            SELECT add_compression_policy(
                '{table_name}',
                interval '{compress_after}'
                {if_not_exists_clause}
            );
            """
            await session.execute(sql)
            await session.commit()
            
        logger.info(f"Added compression policy to {table_name} after {compress_after}")
        
    async def add_retention_policy(
        self,
        table_name: str,
        drop_after: str = "365 days",
    ) -> None:
        """
        Add a retention policy to a hypertable.
        
        Args:
            table_name: Name of the hypertable
            drop_after: When to drop chunks (e.g., '90 days')
        """
        async with self.session_scope() as session:
            sql = f"""
            SELECT add_retention_policy(
                '{table_name}',
                interval '{drop_after}'
            );
            """
            await session.execute(sql)
            await session.commit()
            
        logger.info(f"Added retention policy to {table_name} after {drop_after}")

    async def get_session(self) -> AsyncSession:
        """
        Get an async database session.

        Returns:
            SQLAlchemy AsyncSession
        """
        return self.async_session_maker()

    @asynccontextmanager
    async def session_scope(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Async session scope context manager for automatic commit/rollback.

        Yields:
            SQLAlchemy AsyncSession

        Example:
            ```
            async with db.session_scope() as session:
                session.add(model)
                # No need to commit - handled by context manager
            ```
        """
        session = await self.get_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Session error")
            raise
        finally:
            await session.close()


async def initialize_async_database(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
) -> AsyncDatabase:
    """
    Initialize an async database connection.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database username
        password: Database password

    Returns:
        AsyncDatabase connection manager instance
    """
    db_url = await create_database_url(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )

    db = AsyncDatabase(db_url)
    
    await db.create_database_tables()
    await db.initialize_timescale_extension()
        
    # Import here to avoid circular imports
    from src.data.storage.models.market_data import MarketDataModel
    from src.data.storage.timescale_utils import setup_hypertables
    
    # Set up hypertables for time-series data
    time_series_models = [
        MarketDataModel,  # Market data (candlesticks)
        # Add other time-series models here as needed
    ]
    
    await setup_hypertables(
        db=db,
        models=time_series_models,
        time_column="timestamp",  # Use timestamp column for time index
        chunk_interval="1 day",   # Store each day in a separate chunk
        compress_after="7 days",  # Compress data after 7 days
        retention_period="365 days",  # Keep data for 1 year
    )
    
    logger.info("TimescaleDB hypertables initialized")

    return db