"""setup_timescale_hypertables

Revision ID: fa708376b6c3
Revises: 21f763952ce5
Create Date: 2025-04-04 21:54:42.437302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'fa708376b6c3'
down_revision: Union[str, None] = '6a43465030be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema to implement TimescaleDB hypertables.
    
    This migration:
    1. Ensures TimescaleDB extension is installed
    2. Converts market_data table to a hypertable
    3. Sets up compression policy for market_data
    4. Converts system_logs table to a hypertable with retention policy
    """
    # Create connection
    conn = op.get_bind()
    
    # Enable TimescaleDB extension
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
    
    # Define hypertable settings for each time-series table
    hypertables = [
        {
            "name": "market_data", 
            "time_column": "timestamp",
            "chunk_interval": "1 day",
            "compress_after": "30 days",
            "has_retention": False,
            "partitioning_columns": ["symbol", "interval"]
        },
        {
            "name": "trade_data", 
            "time_column": "timestamp",
            "chunk_interval": "1 day",
            "compress_after": "30 days",
            "has_retention": False,
            "partitioning_columns": ["symbol"]
        },
        {
            "name": "system_logs", 
            "time_column": "created_at",
            "chunk_interval": "1 day",
            "compress_after": "30 days",
            "retention_period": "180 days",
            "has_retention": True,
            "partitioning_columns": ["id"]
        }
        # Add other time-series tables here as needed
    ]
    
    # Setup each hypertable
    for table in hypertables:
        # Get primary space partitioning column (first in the list)
        primary_space_column = table["partitioning_columns"][0] if table["partitioning_columns"] else None
        
        # Convert to hypertable with first partitioning column if available
        hypertable_sql = f"""
        SELECT create_hypertable(
            '{table["name"]}', 
            '{table["time_column"]}',
            {f"partitioning_column => '{primary_space_column}', number_partitions => 4," if primary_space_column else ""}
            if_not_exists => TRUE,            
            chunk_time_interval => interval '{table["chunk_interval"]}'
        );
        """
        conn.execute(text(hypertable_sql))
        
        # Add additional dimensions for any remaining partitioning columns
        if len(table["partitioning_columns"]) > 1:
            for column in table["partitioning_columns"][1:]:
                conn.execute(text(f"""
                SELECT add_dimension(
                    '{table["name"]}', 
                    '{column}',
                    number_partitions => 4
                );
                """))
        
        # Enable compression
        conn.execute(text(f"""
        ALTER TABLE {table["name"]} SET (timescaledb.compress = true);
        """))
        
        # Add compression policy
        conn.execute(text(f"""
        SELECT add_compression_policy(
            '{table["name"]}', 
            interval '{table["compress_after"]}',
            if_not_exists => TRUE
        );
        """))
        
        # Add retention policy only if specified
        if table["has_retention"]:
            conn.execute(text(f"""
            SELECT add_retention_policy(
                '{table["name"]}', 
                interval '{table["retention_period"]}'
            );
            """))
            print(f"TimescaleDB hypertable with retention setup complete for {table['name']}")
        else:
            print(f"TimescaleDB hypertable without retention setup complete for {table['name']}")
    
    print("TimescaleDB hypertables setup complete")


def downgrade() -> None:
    """
    Downgrade schema to remove TimescaleDB configurations.
    
    This migration:
    1. Removes retention policies where applicable
    2. Removes compression policies
    3. Does NOT remove the extension or convert tables back to regular tables
       (this would result in data loss)
    """
    # Create connection
    conn = op.get_bind()
    
    # Define tables to remove TimescaleDB settings from
    tables_with_retention = ["system_logs"]
    all_tables = ["market_data", "trade_data", "system_logs"]
    
    # Remove retention policies where applicable
    for table in tables_with_retention:
        conn.execute(text(f"""
        SELECT remove_retention_policy('{table}', if_exists => TRUE);
        """))
        print(f"Retention policy removed for {table}")
    
    # Remove compression policies for all tables
    for table in all_tables:
        conn.execute(text(f"""
        SELECT remove_compression_policy('{table}', if_exists => TRUE);
        """))
        print(f"Compression policy removed for {table}")
    
    print("TimescaleDB hypertables downgrade complete")
