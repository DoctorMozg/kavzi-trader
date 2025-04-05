"""
Database connection and session management for KavziTrader.

This module provides utilities for establishing asynchronous database connections,
managing sessions, and handling transactions with SQLAlchemy.
Includes support for TimescaleDB hypertables for time-series data.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

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
    logger.debug(f"Creating async engine for {db_url}")
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
        db_url_str = db_url.render_as_string(hide_password=True)
        logger.info(
            f"Async database connection to {db_url_str} initializing",
        )
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
        logger.info(
            f"Async database connection to {db_url_str} established",
        )

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

    return AsyncDatabase(db_url)
