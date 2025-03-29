"""
Incremental update manager for historical data collection.

This module provides functionality for managing incremental updates 
of historical market data, including gap detection and filling.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.api.binance.constants import KLINE_INTERVALS
from src.data.collection.config.schemas import IncrementalUpdateConfigSchema
from src.data.storage.database import Database
from src.data.storage.models.market_data import MarketDataModel

logger = logging.getLogger(__name__)


class IncrementalUpdateManager:
    """
    Manages incremental updates for historical data.
    
    This class:
    1. Determines the last timestamp in the database for each symbol/interval
    2. Calculates what data needs to be fetched
    3. Detects and reports gaps in the data
    """
    
    def __init__(
        self, 
        database: Database,
        config: Optional[IncrementalUpdateConfigSchema] = None
    ):
        """
        Initialize the incremental update manager.
        
        Args:
            database: The database connection manager
            config: Optional configuration for incremental updates
        """
        self.database = database
        self.config = config or IncrementalUpdateConfigSchema()
        
    def get_last_timestamp(
        self, symbol: str, interval: str, session: Optional[Session] = None
    ) -> Optional[datetime]:
        """
        Get the timestamp of the last record for a symbol and interval.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            session: Database session (optional)
            
        Returns:
            Timestamp of the last record or None if no records exist
        """
        close_session = False
        if session is None:
            session = self.database.get_session()
            close_session = True
            
        try:
            stmt = (
                select(func.max(MarketDataModel.timestamp))
                .where(
                    and_(
                        MarketDataModel.symbol == symbol,
                        MarketDataModel.interval == interval
                    )
                )
            )
            result = session.execute(stmt).scalar_one_or_none()
            return result
        finally:
            if close_session and session:
                session.close()
                
    def calculate_missing_ranges(
        self, 
        symbol: str, 
        interval: str, 
        start_time: datetime,
        end_time: datetime,
        session: Optional[Session] = None
    ) -> List[Tuple[datetime, datetime]]:
        """
        Calculate time ranges that need to be fetched for a complete dataset.
        
        This method determines what data is missing between start_time and end_time
        by checking what data already exists in the database.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            start_time: Start time for required data
            end_time: End time for required data
            session: Database session (optional)
            
        Returns:
            List of (start, end) tuples representing time ranges to fetch
        """
        close_session = False
        if session is None:
            session = self.database.get_session()
            close_session = True
            
        try:
            # Get intervals with data in the specified range
            stmt = (
                select(MarketDataModel.timestamp)
                .where(
                    and_(
                        MarketDataModel.symbol == symbol,
                        MarketDataModel.interval == interval,
                        MarketDataModel.timestamp >= start_time,
                        MarketDataModel.timestamp <= end_time
                    )
                )
                .order_by(MarketDataModel.timestamp.asc())
            )
            existing_timestamps = [row[0] for row in session.execute(stmt).all()]
            
            # If no data exists in the range, return the full range
            if not existing_timestamps:
                return [(start_time, end_time)]
            
            # Convert interval to timedelta
            interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000
            interval_timedelta = timedelta(milliseconds=interval_ms)
            
            # Calculate expected timestamps
            current = start_time
            expected_timestamps = []
            while current <= end_time:
                expected_timestamps.append(current)
                current += interval_timedelta
                
            # Find missing timestamps
            missing_timestamps = set(expected_timestamps) - set(existing_timestamps)
            
            # Group missing timestamps into contiguous ranges
            if not missing_timestamps:
                return []
                
            missing_timestamps = sorted(missing_timestamps)
            ranges = []
            range_start = missing_timestamps[0]
            prev_ts = range_start
            
            for ts in missing_timestamps[1:]:
                # If this timestamp is more than one interval away from previous,
                # close the current range and start a new one
                if (ts - prev_ts) > interval_timedelta * 1.5:
                    ranges.append((range_start, prev_ts))
                    range_start = ts
                prev_ts = ts
                
            # Add the last range
            ranges.append((range_start, prev_ts))
            
            return ranges
        finally:
            if close_session and session:
                session.close()
        
    def detect_gaps(
        self, 
        symbol: str, 
        interval: str, 
        look_back_periods: Optional[int] = None,
        session: Optional[Session] = None
    ) -> List[Tuple[datetime, datetime]]:
        """
        Detect gaps in the historical data.
        
        This method analyzes existing data to find gaps that should be filled.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            look_back_periods: How many periods to look back (default from config)
            session: Database session (optional)
            
        Returns:
            List of (start, end) tuples representing gaps in the data
        """
        close_session = False
        if session is None:
            session = self.database.get_session()
            close_session = True
            
        look_back = look_back_periods or self.config.look_back_periods
        
        try:
            # Get the interval in milliseconds
            interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000
            interval_timedelta = timedelta(milliseconds=interval_ms)
            
            # Query for timestamps, ordered
            stmt = (
                select(MarketDataModel.timestamp)
                .where(
                    and_(
                        MarketDataModel.symbol == symbol,
                        MarketDataModel.interval == interval
                    )
                )
                .order_by(MarketDataModel.timestamp.asc())
            )
            timestamps = [row[0] for row in session.execute(stmt).all()]
            
            if len(timestamps) < 2:
                return []  # Not enough data to detect gaps
                
            # Calculate maximum allowed gap (slightly more than one interval)
            max_gap = interval_timedelta * 1.1
            
            # Find gaps
            gaps = []
            for i in range(1, len(timestamps)):
                gap = timestamps[i] - timestamps[i-1]
                if gap > max_gap:
                    # Calculate the exact range to fill
                    gap_start = timestamps[i-1] + interval_timedelta
                    gap_end = timestamps[i] - interval_timedelta
                    
                    # Only add if there's actually a missing interval
                    if gap_start <= gap_end:
                        gaps.append((gap_start, gap_end))
            
            return gaps
        finally:
            if close_session and session:
                session.close()
                
    def get_update_plan(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Create a plan for updating historical data incrementally.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            start_time: Start time for required data
            end_time: End time for required data
            
        Returns:
            Dictionary containing the update plan with ranges to fetch and statistics
        """
        with self.database.session_scope() as session:
            # Get the last timestamp in the database
            last_timestamp = self.get_last_timestamp(symbol, interval, session)
            
            # If data exists and we're not starting from before the existing data
            if last_timestamp and start_time > last_timestamp:
                # Just fetch from the last timestamp to end_time
                ranges_to_fetch = [(last_timestamp, end_time)]
            else:
                # Calculate missing ranges in the requested period
                ranges_to_fetch = self.calculate_missing_ranges(
                    symbol, interval, start_time, end_time, session
                )
            
            # Detect any gaps in the existing data
            gaps = self.detect_gaps(symbol, interval, session=session)
            
            # Add gaps to ranges_to_fetch if auto_fill_gaps is enabled
            if self.config.auto_fill_gaps and gaps:
                ranges_to_fetch.extend(gaps)
                # Sort and merge overlapping ranges
                if ranges_to_fetch:
                    ranges_to_fetch.sort(key=lambda x: x[0])
                    merged_ranges = []
                    current_start, current_end = ranges_to_fetch[0]
                    
                    for next_start, next_end in ranges_to_fetch[1:]:
                        if next_start <= current_end:
                            # Ranges overlap, merge them
                            current_end = max(current_end, next_end)
                        else:
                            # No overlap, add current range and start a new one
                            merged_ranges.append((current_start, current_end))
                            current_start, current_end = next_start, next_end
                    
                    # Add the last range
                    merged_ranges.append((current_start, current_end))
                    ranges_to_fetch = merged_ranges
            
            # Calculate statistics
            total_ranges = len(ranges_to_fetch)
            interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000
            
            estimated_records = 0
            for start, end in ranges_to_fetch:
                range_ms = (end - start).total_seconds() * 1000
                estimated_records += (range_ms / interval_ms) + 1  # +1 to include both endpoints
                
            return {
                "symbol": symbol,
                "interval": interval,
                "ranges_to_fetch": ranges_to_fetch,
                "gaps_detected": len(gaps),
                "total_ranges": total_ranges,
                "estimated_records": int(estimated_records),
                "has_existing_data": last_timestamp is not None
            } 