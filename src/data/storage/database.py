"""
Database connection and session management for KavziTrader.

This module provides utilities for establishing database connections,
managing sessions, and handling transactions with SQLAlchemy.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Create a base class for SQLAlchemy models
Base = declarative_base()


def create_database_url(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    ssl_mode: str = "disable",
) -> URL:
    """
    Create a SQLAlchemy database URL for PostgreSQL.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database username
        password: Database password
        ssl_mode: SSL mode for connection

    Returns:
        SQLAlchemy URL object
    """
    return URL.create(
        drivername="postgresql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
        query={"sslmode": ssl_mode},
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
    return create_engine(
        db_url,
        echo=echo,
        pool_pre_ping=True,  # Check connection before using from pool
        pool_recycle=3600,  # Recycle connections after 1 hour
    )


class Database:
    """
    Database connection manager for KavziTrader.

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
        self.engine = create_db_engine(db_url, echo)
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        db_url_str = db_url.render_as_string(hide_password=True)
        logger.info(
            f"Database connection established to {db_url_str}",
        )

    def create_database_tables(self) -> None:
        """Create all tables defined in SQLAlchemy models."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created")

    def get_session(self) -> Session:
        """
        Get a database session.

        Returns:
            SQLAlchemy session
        """
        return self.SessionLocal()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        Session scope context manager for automatic commit/rollback.

        Yields:
            SQLAlchemy session

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
    ssl_mode: str = "disable",
) -> Database:
    """
    Initialize a database connection.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database username
        password: Database password
        ssl_mode: SSL mode for connection
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
        ssl_mode=ssl_mode,
    )

    return Database(db_url)
