#!/usr/bin/env python
"""
Test script for the historical data collection system.

This script demonstrates how to use the historical data collection
system programmatically.
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the project root to the path so we can import from src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.commons.logging import setup_logging
from src.commons.time_utility import utc_now
from src.data.collection.historical.fetcher import HistoricalDataFetcher
from src.data.storage.database import initialize_database

# Set up logging
logger = setup_logging(name="kavzitrader", log_level="INFO")


def test_historical_data_fetch():
    """Test historical data fetching."""
    # Initialize the database connection
    database = initialize_database(
        host="localhost",
        port=5432,
        database="kavzitrader",
        user="postgres",
        password="postgres",
    )
    
    # Create the fetcher
    fetcher = HistoricalDataFetcher(
        database=database,
        batch_size=1000,
        max_workers=4,
    )
    
    # Set up test parameters
    symbol = "BTCUSDT"
    interval = "1h"
    end_time = utc_now()
    start_time = end_time - timedelta(days=7)  # Last 7 days
    
    print(f"Fetching historical data for {symbol} {interval}")
    print(f"Time range: {start_time} to {end_time}")
    
    # Fetch the data
    result = fetcher.fetch_historical_data(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        force_full=False,  # Use incremental update
        validate=True,
        store_csv=False,
    )
    
    # Print results
    print("\nFetch results:")
    print(f"Records processed: {result.get('records_processed', 0)}")
    print(f"Records inserted: {result.get('records_inserted', 0)}")
    print(f"Records updated: {result.get('records_updated', 0)}")
    
    if "validation" in result:
        print("\nValidation results:")
        if result['validation']['valid']:
            print("✅ All data is valid")
        else:
            print("⚠️ Validation issues found:")
            for issue in result['validation']['issues']:
                print(f"- {issue}")
        
        if result['validation']['warnings']:
            print("\nValidation warnings:")
            for warning in result['validation']['warnings'][:5]:
                print(f"- {warning}")
            
            if len(result['validation']['warnings']) > 5:
                print(f"... and {len(result['validation']['warnings']) - 5} more warnings")
    
    if "metrics" in result:
        metrics = result['metrics']
        print("\nPerformance metrics:")
        print(f"Time taken: {metrics['elapsed_formatted']}")
        print(f"Throughput: {metrics['performance']['throughput_formatted']}")
        print(f"API calls: {metrics['api']['calls']} (errors: {metrics['api']['errors']})")
        print(f"Batches completed: {metrics['batches']['completed']}")
    
    # Get data summary
    summary = fetcher.get_data_summary(symbol, interval)
    print("\nData summary:")
    print(f"First record: {summary.get('first_timestamp')}")
    print(f"Last record: {summary.get('last_timestamp')}")
    print(f"Total records: {summary.get('count', 0)}")
    print(f"Duration: {summary.get('duration_days', 0):.1f} days")
    
    # Validate data integrity
    validation = fetcher.validate_data_integrity(symbol, interval)
    print("\nData integrity validation:")
    if validation['valid']:
        print("✅ Data integrity check passed - no issues found")
    else:
        print("⚠️ Data integrity issues found:")
        for issue in validation['issues']:
            print(f"- {issue}")
    
    if validation['gaps']:
        print(f"\nFound {len(validation['gaps'])} gaps in the data:")
        for i, gap in enumerate(validation['gaps'][:5]):
            print(f"{i+1}. {gap['start']} to {gap['end']} ({gap['duration_hours']:.1f} hours)")
        
        if len(validation['gaps']) > 5:
            print(f"... and {len(validation['gaps']) - 5} more gaps")


if __name__ == "__main__":
    test_historical_data_fetch() 