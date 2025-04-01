#!/usr/bin/env python
"""
Initialize TimescaleDB for KavziTrader.

This script sets up TimescaleDB hypertables for time-series data models.
It should be run after the database tables are created.
"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src.commons.logging import setup_logging
from src.data.storage.database_async import initialize_async_database
from src.data.storage.models.market_data import FeatureModel, MarketDataModel
from src.data.storage.timescale_utils import setup_hypertables

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


async def initialize_timescale_db() -> None:
    """Initialize TimescaleDB hypertables."""
    # Get database connection parameters from environment variables
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    database = os.getenv("POSTGRES_DB", "postgres")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")

    logger.info(f"Connecting to TimescaleDB at {host}:{port}/{database}")

    # Initialize database connection
    db = await initialize_async_database(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )

    # Create tables if they don't exist
    await db.create_database_tables()
    logger.info("Database tables created")

    # Set up hypertables for time-series data
    time_series_models = [
        MarketDataModel,  # Market data (candlesticks)
        # Add other time-series models here
    ]

    # Configure hypertables with appropriate settings
    await setup_hypertables(
        db=db,
        models=time_series_models,
        time_column="timestamp",  # Use timestamp column for time index
        chunk_interval="1 day",   # Store each day in a separate chunk
        compress_after="7 days",  # Compress data after 7 days
        retention_period="365 days",  # Keep data for 1 year
    )

    logger.info("TimescaleDB initialization complete")
