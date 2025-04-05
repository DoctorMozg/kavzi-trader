"""
Synchronous database connector for the models package.

This module provides utilities for establishing synchronous database connections,
managing sessions, and handling transactions with SQLAlchemy.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def create_database_url(
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
        drivername="postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )


def create_db_engine(db_url: URL, echo: bool = False) -> Engine:
    """
    Create a SQLAlchemy engine.

    Args:
        db_url: Database URL
        echo: Whether to echo SQL statements

    Returns:
        SQLAlchemy Engine
    """
    logger.debug(f"Creating sync engine for {db_url}")
    return create_engine(
        db_url,
        echo=echo,
        pool_pre_ping=True,  # Check connection before using from pool
        pool_recycle=3600,  # Recycle connections after 1 hour
    )


class Database:
    """
    Synchronous database connection manager.

    This class provides methods for connecting to the database,
    creating sessions, and executing transactions.
    """

    def __init__(self, db_url: URL, echo: bool = False) -> None:
        """
        Initialize the database connection manager.

        Args:
            db_url: Database URL
            echo: Whether to echo SQL statements
        """
        logger.info("Sync database connection initializing")
        self.engine = create_engine(
            db_url,
            echo=echo,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self.session_maker = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            expire_on_commit=False,
        )
        logger.info("Sync database connection established")

    def get_session(self) -> Session:
        """
        Get a database session.

        Returns:
            SQLAlchemy Session
        """
        return self.session_maker()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        Session scope context manager for automatic commit/rollback.

        Yields:
            SQLAlchemy Session

        Example:
            ```
            with db.session_scope() as session:
                session.add(model)
                # No need to commit - handled by context manager
            ```
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Session error")
            raise
        finally:
            session.close()


def initialize_database(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    echo: bool = False,
) -> Database:
    """
    Initialize a database connection.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database username
        password: Database password
        echo: Whether to echo SQL statements

    Returns:
        Database connection manager instance
    """
    db_url = create_database_url(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )

    return Database(db_url, echo=echo) 