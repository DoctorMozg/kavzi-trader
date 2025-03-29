"""
Batching utilities for historical data collection.

This module provides utilities for optimizing data collection through
efficient batching strategies and parallel processing.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional, Callable

from src.api.binance.constants import KLINE_INTERVALS

logger = logging.getLogger(__name__)


def calculate_batch_size_for_timeframe(
    interval: str,
    max_records_per_batch: int = 1000,
    target_batch_duration_sec: int = 30
) -> int:
    """
    Calculate optimal batch size for a given timeframe.
    
    This function determines the optimal batch size based on the
    interval and target batch duration, ensuring efficient use
    of API rate limits.
    
    Args:
        interval: Timeframe interval (e.g. "1m", "1h")
        max_records_per_batch: Maximum records per batch
        target_batch_duration_sec: Target duration for each batch in seconds
        
    Returns:
        Optimal batch size
    """
    # Get interval in milliseconds
    interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000
    interval_sec = interval_ms / 1000
    
    # Calculate how many records to fetch to meet the target duration
    records_for_target_duration = math.ceil(target_batch_duration_sec / interval_sec)
    
    # Limit to the maximum records per batch
    return min(records_for_target_duration, max_records_per_batch)


def create_time_batches(
    start_time: datetime,
    end_time: datetime,
    interval: str,
    batch_size: int
) -> List[Tuple[datetime, datetime]]:
    """
    Create time batches for efficient data collection.
    
    This function divides a time range into batches of the specified size,
    taking into account the interval to ensure accurate batch boundaries.
    
    Args:
        start_time: Start time for data collection
        end_time: End time for data collection
        interval: Timeframe interval (e.g. "1m", "1h")
        batch_size: Number of records per batch
        
    Returns:
        List of (batch_start, batch_end) tuples
    """
    # Get interval in milliseconds
    interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000
    interval_timedelta = timedelta(milliseconds=interval_ms)
    
    # Calculate batch duration
    batch_duration = interval_timedelta * batch_size
    
    # Ensure start_time and end_time are aligned to interval boundaries
    aligned_start = start_time
    aligned_end = end_time
    
    # Create batches
    batches = []
    batch_start = aligned_start
    
    while batch_start < aligned_end:
        batch_end = min(batch_start + batch_duration, aligned_end)
        batches.append((batch_start, batch_end))
        batch_start = batch_end
    
    return batches


def optimize_batch_distribution(
    batches: List[Tuple[datetime, datetime]],
    worker_count: int
) -> List[List[Tuple[datetime, datetime]]]:
    """
    Optimize distribution of batches across workers.
    
    This function distributes batches across workers in a way that
    balances the workload and minimizes waiting time.
    
    Args:
        batches: List of (batch_start, batch_end) tuples
        worker_count: Number of workers
        
    Returns:
        List of batch lists, one for each worker
    """
    if not batches:
        return [[] for _ in range(worker_count)]
    
    # If we have fewer batches than workers, adjust worker count
    effective_worker_count = min(worker_count, len(batches))
    
    # Create empty lists for each worker
    worker_batches = [[] for _ in range(effective_worker_count)]
    
    # Sort batches by duration (longest first)
    sorted_batches = sorted(
        batches,
        key=lambda batch: (batch[1] - batch[0]).total_seconds(),
        reverse=True
    )
    
    # Distribute batches using a greedy algorithm
    # Assign each batch to the worker with the least work so far
    for batch in sorted_batches:
        # Find worker with least work
        worker_idx = 0
        min_workload = float('inf')
        
        for i, worker_batch_list in enumerate(worker_batches):
            # Calculate worker's current workload
            workload = sum((b[1] - b[0]).total_seconds() for b in worker_batch_list)
            
            if workload < min_workload:
                min_workload = workload
                worker_idx = i
                
        # Assign batch to this worker
        worker_batches[worker_idx].append(batch)
    
    return worker_batches


def estimate_batch_stats(
    batches: List[Tuple[datetime, datetime]],
    interval: str
) -> Dict[str, Any]:
    """
    Estimate statistics for a set of batches.
    
    This function calculates estimated record counts, duration,
    and other statistics for a set of batches.
    
    Args:
        batches: List of (batch_start, batch_end) tuples
        interval: Timeframe interval (e.g. "1m", "1h")
        
    Returns:
        Dictionary with batch statistics
    """
    if not batches:
        return {
            "batch_count": 0,
            "estimated_records": 0,
            "total_duration_seconds": 0,
            "avg_batch_size": 0,
            "avg_batch_duration_seconds": 0
        }
    
    # Get interval in milliseconds
    interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000
    
    # Calculate statistics
    total_records = 0
    total_duration_seconds = 0
    
    for start, end in batches:
        duration_ms = (end - start).total_seconds() * 1000
        batch_records = math.ceil(duration_ms / interval_ms)
        
        total_records += batch_records
        total_duration_seconds += (end - start).total_seconds()
    
    return {
        "batch_count": len(batches),
        "estimated_records": total_records,
        "total_duration_seconds": total_duration_seconds,
        "avg_batch_size": total_records / len(batches),
        "avg_batch_duration_seconds": total_duration_seconds / len(batches)
    }


def adjust_batch_size_for_rate_limits(
    interval: str,
    initial_batch_size: int,
    weight_per_request: int = 1,
    max_weight_per_minute: int = 1200
) -> int:
    """
    Adjust batch size to comply with API rate limits.
    
    This function ensures that the proposed batch size doesn't exceed
    Binance API rate limits, adjusting if necessary.
    
    Args:
        interval: Timeframe interval (e.g. "1m", "1h")
        initial_batch_size: Initial proposed batch size
        weight_per_request: API weight per request
        max_weight_per_minute: Maximum allowed weight per minute
        
    Returns:
        Adjusted batch size that complies with rate limits
    """
    # Get interval in seconds
    interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000
    interval_sec = interval_ms / 1000
    
    # Calculate how many requests we can make per minute
    max_requests_per_minute = max_weight_per_minute / weight_per_request
    
    # Calculate max records we can fetch per minute
    # This assumes one request per batch
    max_records_per_minute = max_requests_per_minute * initial_batch_size
    
    # Calculate how many records we'd try to fetch per minute with the initial batch size
    records_per_second = initial_batch_size / interval_sec
    records_per_minute = records_per_second * 60
    
    # If we'd exceed the rate limit, adjust the batch size
    if records_per_minute > max_records_per_minute:
        adjusted_batch_size = int(max_records_per_minute / (60 / interval_sec))
        logger.warning(
            f"Batch size adjusted from {initial_batch_size} to {adjusted_batch_size} "
            f"to comply with API rate limits"
        )
        return max(1, adjusted_batch_size)
    
    return initial_batch_size 