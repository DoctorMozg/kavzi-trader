"""
Historical data fetcher for market data collection.

This module provides the main interface for fetching historical market data
from Binance and storing it in the database.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

from src.api.binance.historical import BinanceHistoricalDataClient
from src.api.common.exceptions import APIError, RateLimitError
from src.api.common.models import CandlestickSchema
from src.commons.time_utility import utc_now
from src.data.collection.config.schemas import (
    HistoricalDataFetchConfigSchema, 
    DataValidationConfigSchema,
    IncrementalUpdateConfigSchema
)
from src.data.collection.historical.incremental import IncrementalUpdateManager
from src.data.collection.historical.storage import MarketDataStorage
from src.data.collection.historical.validation import DataValidator
from src.data.collection.utils.batching import (
    create_time_batches, 
    optimize_batch_distribution,
    adjust_batch_size_for_rate_limits
)
from src.data.collection.utils.metrics import CollectionMetrics, timed_execution
from src.data.storage.database import Database

logger = logging.getLogger(__name__)


class HistoricalDataFetcher:
    """
    Main class for fetching and storing historical market data.
    
    This class orchestrates the entire data collection process:
    1. Determines what data needs to be fetched (incremental or full)
    2. Fetches data from Binance using BinanceHistoricalDataClient
    3. Validates and cleans the data
    4. Stores the data in the database
    """
    
    def __init__(
        self,
        database: Database,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        batch_size: int = 1000,
        max_workers: int = 4,
        output_dir: Optional[Path] = None
    ):
        """
        Initialize the historical data fetcher.
        
        Args:
            database: Database connection manager
            api_key: Binance API key (optional)
            api_secret: Binance API secret (optional)
            batch_size: Default batch size for data fetching
            max_workers: Maximum number of parallel workers
            output_dir: Directory for CSV output (if enabled)
        """
        self.database = database
        self.client = BinanceHistoricalDataClient(
            api_key=api_key,
            api_secret=api_secret,
            batch_size=batch_size,
            max_workers=max_workers,
            output_dir=output_dir or Path("./data")
        )
        self.storage = MarketDataStorage(database)
        self.incremental = IncrementalUpdateManager(database)
        self.validator = DataValidator()
        
    @timed_execution
    def fetch_historical_data(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        force_full: bool = False,
        batch_size: Optional[int] = None,
        max_workers: Optional[int] = None,
        validate: bool = True,
        store_csv: bool = False,
        output_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Fetch historical data for a symbol and interval.
        
        Args:
            symbol: Trading pair symbol (e.g. "BTCUSDT")
            interval: Timeframe interval (e.g. "1m", "1h")
            start_time: Start time for data collection
            end_time: End time for data collection (defaults to now)
            force_full: Force full download instead of incremental
            batch_size: Batch size for data fetching (overrides default)
            max_workers: Maximum number of parallel workers (overrides default)
            validate: Whether to validate data during collection
            store_csv: Whether to also store data as CSV
            output_dir: Directory for CSV output (if store_csv is True)
            
        Returns:
            Dictionary with statistics about the operation
        """
        # Create configuration object
        config = HistoricalDataFetchConfigSchema(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time or utc_now(),
            batch_size=batch_size or self.client.batch_size,
            max_workers=max_workers or self.client.max_workers,
            force_full=force_full,
            validate=validate,
            store_csv=store_csv,
            output_dir=output_dir
        )
        
        # Set up metrics collector
        metrics = CollectionMetrics(symbol=symbol, interval=interval)
        metrics.start()
        
        try:
            # Get update plan based on what data needs to be fetched
            if not force_full:
                update_plan = self.incremental.get_update_plan(
                    symbol=symbol,
                    interval=interval,
                    start_time=config.start_time,
                    end_time=config.end_time
                )
                ranges_to_fetch = update_plan["ranges_to_fetch"]
                logger.info(
                    f"Incremental update plan created for {symbol} {interval}: "
                    f"{update_plan['total_ranges']} ranges, "
                    f"~{update_plan['estimated_records']} records"
                )
            else:
                # Full fetch - one continuous range
                ranges_to_fetch = [(config.start_time, config.end_time)]
                logger.info(
                    f"Full data fetch for {symbol} {interval} from "
                    f"{config.start_time} to {config.end_time}"
                )
            
            # If nothing to fetch, return early
            if not ranges_to_fetch:
                logger.info(f"No data to fetch for {symbol} {interval}")
                metrics.stop()
                return {
                    "symbol": symbol,
                    "interval": interval,
                    "start_time": config.start_time,
                    "end_time": config.end_time,
                    "records_processed": 0,
                    "records_inserted": 0,
                    "records_updated": 0,
                    "validation": {"valid": True, "issues": [], "warnings": []},
                    "metrics": metrics.get_summary()
                }
            
            # Adjust batch size for rate limits if needed
            effective_batch_size = adjust_batch_size_for_rate_limits(
                interval=interval,
                initial_batch_size=config.batch_size
            )
            
            # Process each time range that needs to be fetched
            total_processed = 0
            total_inserted = 0
            total_updated = 0
            validation_issues = []
            validation_warnings = []
            
            for time_range_idx, (range_start, range_end) in enumerate(ranges_to_fetch):
                logger.info(
                    f"Fetching range {time_range_idx + 1}/{len(ranges_to_fetch)}: "
                    f"{range_start} to {range_end}"
                )
                
                # Create batches for this range
                batches = create_time_batches(
                    start_time=range_start,
                    end_time=range_end,
                    interval=interval,
                    batch_size=effective_batch_size
                )
                
                # Skip if no batches
                if not batches:
                    continue
                    
                # Optimize batch distribution across workers
                worker_batches = optimize_batch_distribution(
                    batches=batches,
                    worker_count=config.max_workers
                )
                
                # Process batches with worker pool
                for worker_idx, batch_list in enumerate(worker_batches):
                    if not batch_list:
                        continue
                        
                    logger.info(
                        f"Worker {worker_idx + 1}/{len(worker_batches)}: "
                        f"Processing {len(batch_list)} batches"
                    )
                    
                    batch_results = self._process_batch_list(
                        symbol=symbol,
                        interval=interval,
                        batch_list=batch_list,
                        validate=config.validate,
                        store_csv=config.store_csv,
                        output_dir=config.output_dir
                    )
                    
                    # Update metrics
                    total_processed += batch_results["records_processed"]
                    total_inserted += batch_results["records_inserted"]
                    total_updated += batch_results["records_updated"]
                    validation_issues.extend(batch_results["validation_issues"])
                    validation_warnings.extend(batch_results["validation_warnings"])
                    
                    metrics.add_batch(
                        processed=batch_results["records_processed"],
                        inserted=batch_results["records_inserted"],
                        updated=batch_results["records_updated"],
                        api_calls=batch_results["api_calls"],
                        api_errors=batch_results["api_errors"],
                        validation_warnings=len(batch_results["validation_warnings"]),
                        validation_errors=len(batch_results["validation_issues"]),
                        batch_time=batch_results.get("execution_time")
                    )
            
            metrics.stop()
            metrics.log_summary()
            
            return {
                "symbol": symbol,
                "interval": interval,
                "start_time": config.start_time,
                "end_time": config.end_time,
                "records_processed": total_processed,
                "records_inserted": total_inserted,
                "records_updated": total_updated,
                "validation": {
                    "valid": len(validation_issues) == 0,
                    "issues": validation_issues,
                    "warnings": validation_warnings
                },
                "metrics": metrics.get_summary()
            }
        except Exception as e:
            logger.exception(f"Error fetching historical data for {symbol} {interval}: {e}")
            metrics.stop()
            
            return {
                "symbol": symbol,
                "interval": interval,
                "start_time": config.start_time,
                "end_time": config.end_time,
                "error": str(e),
                "metrics": metrics.get_summary()
            }
    
    @timed_execution
    def _process_batch_list(
        self,
        symbol: str,
        interval: str,
        batch_list: List[Tuple[datetime, datetime]],
        validate: bool = True,
        store_csv: bool = False,
        output_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Process a list of batches for a symbol and interval.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            batch_list: List of (start_time, end_time) batch tuples
            validate: Whether to validate data
            store_csv: Whether to store as CSV
            output_dir: Directory for CSV output
            
        Returns:
            Dictionary with results of batch processing
        """
        results = {
            "records_processed": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "api_calls": 0,
            "api_errors": 0,
            "validation_issues": [],
            "validation_warnings": []
        }
        
        # Process each batch
        for batch_idx, (batch_start, batch_end) in enumerate(batch_list):
            logger.debug(
                f"Processing batch {batch_idx + 1}/{len(batch_list)}: "
                f"{batch_start} to {batch_end}"
            )
            
            # Fetch data from Binance
            try:
                candlesticks = self._fetch_batch(
                    symbol=symbol,
                    interval=interval,
                    start_time=batch_start,
                    end_time=batch_end
                )
                
                results["api_calls"] += 1
                results["records_processed"] += len(candlesticks)
                
                # Validate if enabled
                if validate and candlesticks:
                    validation_report = self.validator.validate_candlesticks(
                        candlesticks=candlesticks,
                        symbol=symbol,
                        interval=interval
                    )
                    
                    if not validation_report["valid"]:
                        results["validation_issues"].extend(validation_report["issues"])
                    
                    if validation_report["warnings"]:
                        results["validation_warnings"].extend(validation_report["warnings"])
                
                # Store in database
                if candlesticks:
                    storage_result = self.storage.store_candlesticks(
                        candlesticks=candlesticks,
                        symbol=symbol,
                        interval=interval
                    )
                    
                    results["records_inserted"] += storage_result.get("inserted", 0)
                    results["records_updated"] += storage_result.get("updated", 0)
                    
                    # Store as CSV if enabled
                    if store_csv and output_dir:
                        self.client._save_data(
                            data=candlesticks,
                            symbol=symbol,
                            data_type="klines",
                            interval=interval,
                            start_time=batch_start,
                            end_time=batch_end,
                            output_dir=output_dir
                        )
                        
            except RateLimitError:
                # Handle rate limiting by slowing down
                logger.warning(f"Rate limit hit, sleeping for 30 seconds")
                results["api_errors"] += 1
                time.sleep(30)
                
            except APIError as e:
                # Log API errors but continue with other batches
                logger.error(f"API error for {symbol} {interval}: {e}")
                results["api_errors"] += 1
                
            except Exception as e:
                # Log unexpected errors but continue with other batches
                logger.exception(f"Error processing batch: {e}")
                results["api_errors"] += 1
        
        return results
    
    def _fetch_batch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[CandlestickSchema]:
        """
        Fetch a single batch of candlestick data.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            start_time: Start time for the batch
            end_time: End time for the batch
            
        Returns:
            List of candlestick data
        """
        # Convert to milliseconds for the API
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        # Fetch the data
        klines = self.client.client.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_ms,
            end_time=end_ms,
            limit=1000  # API maximum
        )
        
        # Convert to CandlestickSchema objects
        return [
            CandlestickSchema.model_validate({
                "open_time": datetime.fromtimestamp(kline[0] / 1000),
                "open": kline[1],
                "high": kline[2],
                "low": kline[3],
                "close": kline[4],
                "volume": kline[5],
                "close_time": datetime.fromtimestamp(kline[6] / 1000),
                "quote_volume": kline[7],
                "trades": kline[8],
                "taker_buy_base_volume": kline[9],
                "taker_buy_quote_volume": kline[10]
            })
            for kline in klines
        ]
        
    def get_data_summary(
        self,
        symbol: str,
        interval: str
    ) -> Dict[str, Any]:
        """
        Get a summary of available historical data.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            
        Returns:
            Dictionary with data summary
        """
        return self.storage.get_data_summary(symbol, interval)
        
    def validate_data_integrity(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Validate the integrity of stored historical data.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            start_time: Start of range to validate (optional)
            end_time: End of range to validate (optional)
            
        Returns:
            Dictionary with validation results
        """
        with self.database.session_scope() as session:
            # Get existing timestamps
            timestamps = self.storage.get_existing_timestamps(
                symbol=symbol,
                interval=interval,
                start_time=start_time or datetime(2017, 1, 1),
                end_time=end_time or utc_now(),
                session=session
            )
            
            if not timestamps:
                return {
                    "valid": True,
                    "symbol": symbol,
                    "interval": interval,
                    "count": 0,
                    "issues": [],
                    "gaps": []
                }
            
            # Detect gaps using the incremental update manager
            gaps = self.incremental.detect_gaps(
                symbol=symbol,
                interval=interval,
                session=session
            )
            
            # Count total records
            count = len(timestamps)
            
            # Check if we have the expected number of records
            if start_time and end_time:
                # Calculate expected number of records
                from src.api.binance.constants import KLINE_INTERVALS
                interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000
                expected_records = (end_time - start_time).total_seconds() * 1000 / interval_ms
                expected_records = int(expected_records) + 1  # +1 to include both endpoints
                
                record_count_issue = None
                if count < expected_records * 0.95:  # Allow for some missing records (5%)
                    record_count_issue = (
                        f"Insufficient records: {count} found, {expected_records} expected "
                        f"({count / expected_records * 100:.1f}%)"
                    )
                    
            else:
                record_count_issue = None
                
            # Format gaps for reporting
            formatted_gaps = [
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "duration_hours": (end - start).total_seconds() / 3600
                }
                for start, end in gaps
            ]
            
            # Build issues list
            issues = []
            if record_count_issue:
                issues.append(record_count_issue)
                
            if gaps:
                for gap in formatted_gaps:
                    issues.append(
                        f"Gap from {gap['start']} to {gap['end']} "
                        f"({gap['duration_hours']:.1f} hours)"
                    )
            
            return {
                "valid": len(issues) == 0,
                "symbol": symbol,
                "interval": interval,
                "count": count,
                "issues": issues,
                "gaps": formatted_gaps
            } 