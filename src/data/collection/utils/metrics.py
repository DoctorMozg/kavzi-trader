"""
Metrics for historical data collection.

This module provides utilities for tracking and reporting metrics
related to historical data collection performance.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)


class CollectionMetrics:
    """
    Metrics collector for data collection operations.
    
    This class:
    1. Measures execution time of collection operations
    2. Tracks counts of records processed, inserted, and updated
    3. Calculates throughput statistics
    4. Provides reporting functions for collection metrics
    """
    
    def __init__(self, symbol: str = "", interval: str = ""):
        """
        Initialize the collection metrics tracker.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
        """
        self.symbol = symbol
        self.interval = interval
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.records_processed = 0
        self.records_inserted = 0
        self.records_updated = 0
        self.api_calls = 0
        self.api_errors = 0
        self.validation_warnings = 0
        self.validation_errors = 0
        self.batches_completed = 0
        self.batch_times: List[float] = []
        
    def start(self) -> None:
        """Start tracking metrics for a collection operation."""
        self.start_time = time.time()
        logger.info(f"Started collection metrics for {self.symbol} {self.interval}")
        
    def stop(self) -> None:
        """Stop tracking metrics for a collection operation."""
        self.end_time = time.time()
        logger.info(f"Stopped collection metrics for {self.symbol} {self.interval}")
        
    def add_batch(
        self, 
        processed: int = 0, 
        inserted: int = 0, 
        updated: int = 0,
        api_calls: int = 0,
        api_errors: int = 0,
        validation_warnings: int = 0,
        validation_errors: int = 0,
        batch_time: Optional[float] = None
    ) -> None:
        """
        Add metrics for a completed batch.
        
        Args:
            processed: Number of records processed
            inserted: Number of records inserted
            updated: Number of records updated
            api_calls: Number of API calls made
            api_errors: Number of API errors encountered
            validation_warnings: Number of validation warnings
            validation_errors: Number of validation errors
            batch_time: Time taken for the batch (seconds)
        """
        self.records_processed += processed
        self.records_inserted += inserted
        self.records_updated += updated
        self.api_calls += api_calls
        self.api_errors += api_errors
        self.validation_warnings += validation_warnings
        self.validation_errors += validation_errors
        self.batches_completed += 1
        
        if batch_time is not None:
            self.batch_times.append(batch_time)
            
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the collection metrics.
        
        Returns:
            Dictionary with summary metrics
        """
        elapsed = 0.0
        if self.start_time:
            end = self.end_time or time.time()
            elapsed = end - self.start_time
            
        throughput = 0.0
        if elapsed > 0:
            throughput = self.records_processed / elapsed
            
        avg_batch_time = 0.0
        if self.batch_times:
            avg_batch_time = sum(self.batch_times) / len(self.batch_times)
            
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": datetime.fromtimestamp(self.start_time) if self.start_time else None,
            "end_time": datetime.fromtimestamp(self.end_time) if self.end_time else None,
            "elapsed_seconds": elapsed,
            "elapsed_formatted": str(timedelta(seconds=int(elapsed))),
            "records": {
                "processed": self.records_processed,
                "inserted": self.records_inserted,
                "updated": self.records_updated
            },
            "api": {
                "calls": self.api_calls,
                "errors": self.api_errors,
                "error_rate": (self.api_errors / self.api_calls * 100) if self.api_calls > 0 else 0
            },
            "validation": {
                "warnings": self.validation_warnings,
                "errors": self.validation_errors
            },
            "batches": {
                "completed": self.batches_completed,
                "avg_time": avg_batch_time,
                "avg_records": (self.records_processed / self.batches_completed) 
                    if self.batches_completed > 0 else 0
            },
            "performance": {
                "throughput": throughput,
                "throughput_formatted": f"{throughput:.2f} records/second"
            }
        }
        
    def log_summary(self, level: int = logging.INFO) -> None:
        """
        Log a summary of the collection metrics.
        
        Args:
            level: Logging level to use
        """
        summary = self.get_summary()
        
        logger.log(level, f"Collection completed for {self.symbol} {self.interval}")
        logger.log(level, f"Time: {summary['elapsed_formatted']}")
        logger.log(level, f"Records: {summary['records']['processed']} "
                         f"(inserted: {summary['records']['inserted']}, "
                         f"updated: {summary['records']['updated']})")
        logger.log(level, f"API calls: {summary['api']['calls']} "
                         f"(errors: {summary['api']['errors']}, "
                         f"rate: {summary['api']['error_rate']:.2f}%)")
        logger.log(level, f"Validation: {summary['validation']['warnings']} warnings, "
                         f"{summary['validation']['errors']} errors")
        logger.log(level, f"Throughput: {summary['performance']['throughput_formatted']}")


def timed_execution(func: Callable) -> Callable:
    """
    Decorator for timing the execution of a function.
    
    Args:
        func: The function to time
    
    Returns:
        Wrapped function with timing
    """
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        
        # Get the function name for logging
        func_name = func.__name__
        logger.debug(f"Execution time for {func_name}: {elapsed:.4f} seconds")
        
        # If the result is a dict, add the execution time
        if isinstance(result, dict):
            result["execution_time"] = elapsed
            
        return result
    return wrapper 