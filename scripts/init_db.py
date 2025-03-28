#!/usr/bin/env python3

"""
Database initialization script for KavziTrader.

This script creates the database, applies migrations, and seeds initial data.
"""

import logging
import subprocess
import sys
from pathlib import Path

import click
import psycopg2

# Add the project root directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.storage.database import Database, initialize_database
from src.data.storage.models import SystemConfigModel

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("init_db")


def create_database(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
) -> None:
    """
    Create the PostgreSQL database if it doesn't exist.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database username
        password: Database password
    """
    # Connect to default postgres database to check if our database exists
    connection_string = (
        f"host={host} port={port} user={user} password={password} dbname=postgres"
    )

    try:
        conn = psycopg2.connect(connection_string)
        conn.autocommit = True

        with conn.cursor() as cursor:
            # Check if database exists
            cursor.execute(
                f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{database}'",
            )
            exists = cursor.fetchone()

            if not exists:
                logger.info(f"Creating database {database}...")
                cursor.execute(f"CREATE DATABASE {database}")
                logger.info(f"Database {database} created successfully")
            else:
                logger.info(f"Database {database} already exists")

        conn.close()
    except Exception:
        logger.exception("Failed to create database")
        raise


def apply_migrations() -> None:
    """Apply Alembic migrations."""
    logger.info("Applying database migrations...")

    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info(f"Migrations applied successfully:\n{result.stdout}")
    except subprocess.CalledProcessError:
        logger.exception("Failed to apply migrations")
        raise


def seed_system_config(db: Database) -> None:
    """
    Seed initial system configuration.

    Args:
        db: Database connection
    """
    logger.info("Seeding system configuration...")

    with db.session_scope() as session:
        # Add initial system configuration
        configs = [
            {
                "key": "system.version",
                "value": "0.1.0",
                "description": "KavziTrader system version",
                "is_editable": False,
            },
            {
                "key": "logging.level",
                "value": "INFO",
                "description": "Default logging level for the system",
                "is_editable": True,
            },
            {
                "key": "data.default_interval",
                "value": "1h",
                "description": "Default interval for market data",
                "is_editable": True,
            },
        ]

        for config in configs:
            SystemConfigModel.set_value(
                session,
                key=config["key"],
                value=config["value"],
                description=config["description"],
                is_editable=config["is_editable"],
            )

    logger.info("System configuration seeded successfully")


@click.command()
@click.option("--host", default="localhost", help="Database host")
@click.option("--port", type=int, default=5432, help="Database port")
@click.option("--database", default="kavzitrader", help="Database name")
@click.option("--user", default="postgres", help="Database username")
@click.option("--password", default="postgres", help="Database password")
@click.option("--ssl-mode", default="disable", help="SSL mode")
@click.option("--no-create", is_flag=True, help="Skip database creation")
@click.option("--no-migrations", is_flag=True, help="Skip migrations")
@click.option("--no-seed", is_flag=True, help="Skip data seeding")
@click.option("--echo", is_flag=True, help="Echo SQL statements")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def init_db(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    ssl_mode: str,
    no_create: bool,
    no_migrations: bool,
    no_seed: bool,
    echo: bool,
    verbose: bool,
) -> None:
    """Initialize the KavziTrader database system.

    This command creates the database, applies migrations, and seeds initial data.
    """
    # Set verbose logging if requested
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    # Create database if requested
    if not no_create:
        create_database(host, port, database, user, password)

    # Apply migrations if requested
    if not no_migrations:
        apply_migrations()

    # Initialize database connection
    db = initialize_database(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        ssl_mode=ssl_mode,
        echo=echo,
    )

    # Seed data if requested
    if not no_seed:
        seed_system_config(db)

    logger.info("Database initialization completed successfully")
    click.echo("Database initialization completed successfully")


if __name__ == "__main__":
    init_db()
