"""
Storage manager for historical market data.

This module provides functionality for storing market data in the database,
including bulk inserts and updates.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.api.common.models import CandlestickSchema
from src.data.storage.database import Database
from src.data.storage.models.market_data import MarketDataModel

logger = logging.getLogger(__name__)


class MarketDataStorage:
    """
    Handles storage of market data in the database.
    
    This class:
    1. Converts API models to database models
    2. Performs bulk inserts and updates
    3. Optimizes database operations for time-series data
    """
    
    def __init__(self, database: Database):
        """
        Initialize the market data storage.
        
        Args:
            database: The database connection manager
        """
        self.database = database
    
    def store_candlesticks(
        self, 
        candlesticks: List[CandlestickSchema], 
        symbol: str,
        interval: str,
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Store candlesticks in the database.
        
        Args:
            candlesticks: List of candlestick data
            symbol: Trading pair symbol
            interval: Timeframe interval
            session: Database session (optional)
            
        Returns:
            Statistics about the storage operation
        """
        if not candlesticks:
            return {"inserted": 0, "updated": 0, "total": 0}
        
        close_session = False
        if session is None:
            session = self.database.get_session()
            close_session = True
        
        try:
            # Convert CandlestickSchema objects to MarketDataModel objects
            market_data_models = [
                self.candlestick_to_model(c, symbol, interval)
                for c in candlesticks
            ]
            
            # Initial statistics
            stats = {
                "total": len(market_data_models),
                "inserted": 0,
                "updated": 0
            }
            
            # Use PostgreSQL's ON CONFLICT DO UPDATE for efficient upsert
            stmt = insert(MarketDataModel).values(
                [m.model_dump_dict() for m in market_data_models]
            )
            
            # Use the symbol, interval, and timestamp as the conflict target
            # (These should have a unique constraint)
            stmt = stmt.on_conflict_do_update(
                constraint="uix_market_data_symbol_interval_timestamp",
                set_={
                    "opened": stmt.excluded.opened,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "closed": stmt.excluded.closed,
                    "volume": stmt.excluded.volume,
                    "quote_volume": stmt.excluded.quote_volume,
                    "trades": stmt.excluded.trades,
                    "taker_buy_base_volume": stmt.excluded.taker_buy_base_volume,
                    "taker_buy_quote_volume": stmt.excluded.taker_buy_quote_volume,
                    "updated_at": datetime.utcnow()
                }
            )
            
            # Execute the statement
            result = session.execute(stmt)
            session.commit()
            
            # Update statistics based on the result
            if hasattr(result, 'rowcount'):
                # PostgreSQL returns the number of rows inserted or updated
                stats["inserted"] = result.rowcount
            else:
                # Check how many records actually exist now
                timestamp_list = [c.open_time for c in candlesticks]
                existing_count = session.execute(
                    select(MarketDataModel)
                    .where(
                        and_(
                            MarketDataModel.symbol == symbol,
                            MarketDataModel.interval == interval,
                            MarketDataModel.timestamp.in_(timestamp_list)
                        )
                    )
                ).rowcount
                
                stats["inserted"] = existing_count
            
            return stats
            
        finally:
            if close_session and session:
                session.close()
    
    def candlestick_to_model(
        self, 
        candlestick: CandlestickSchema,
        symbol: str,
        interval: str
    ) -> MarketDataModel:
        """
        Convert a CandlestickSchema to a MarketDataModel.
        
        Args:
            candlestick: Candlestick data
            symbol: Trading pair symbol
            interval: Timeframe interval
            
        Returns:
            MarketDataModel instance
        """
        return MarketDataModel(
            symbol=symbol,
            interval=interval,
            timestamp=candlestick.open_time,
            opened=Decimal(str(candlestick.open)),
            high=Decimal(str(candlestick.high)),
            low=Decimal(str(candlestick.low)),
            closed=Decimal(str(candlestick.close)),
            volume=Decimal(str(candlestick.volume)),
            quote_volume=Decimal(str(candlestick.quote_volume)) if candlestick.quote_volume else None,
            trades=candlestick.trades,
            taker_buy_base_volume=Decimal(str(candlestick.taker_buy_base_volume)) 
                if candlestick.taker_buy_base_volume else None,
            taker_buy_quote_volume=Decimal(str(candlestick.taker_buy_quote_volume))
                if candlestick.taker_buy_quote_volume else None
        )
    
    def get_existing_timestamps(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        session: Optional[Session] = None
    ) -> List[datetime]:
        """
        Get timestamps of existing records in a time range.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            start_time: Start of time range
            end_time: End of time range
            session: Database session (optional)
            
        Returns:
            List of timestamps for existing records
        """
        close_session = False
        if session is None:
            session = self.database.get_session()
            close_session = True
        
        try:
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
            
            result = session.execute(stmt).all()
            return [row[0] for row in result]
        finally:
            if close_session and session:
                session.close()
    
    def delete_range(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        session: Optional[Session] = None
    ) -> int:
        """
        Delete market data in a specific time range.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            start_time: Start of time range
            end_time: End of time range
            session: Database session (optional)
            
        Returns:
            Number of records deleted
        """
        close_session = False
        if session is None:
            session = self.database.get_session()
            close_session = True
        
        try:
            stmt = (
                MarketDataModel.__table__.delete()
                .where(
                    and_(
                        MarketDataModel.symbol == symbol,
                        MarketDataModel.interval == interval,
                        MarketDataModel.timestamp >= start_time,
                        MarketDataModel.timestamp <= end_time
                    )
                )
            )
            
            result = session.execute(stmt)
            session.commit()
            
            return result.rowcount
        finally:
            if close_session and session:
                session.close()
    
    def get_data_count(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        session: Optional[Session] = None
    ) -> int:
        """
        Get count of market data records for a symbol and interval.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            session: Database session (optional)
            
        Returns:
            Number of records
        """
        close_session = False
        if session is None:
            session = self.database.get_session()
            close_session = True
        
        try:
            query = select(func.count(MarketDataModel.id)).where(
                and_(
                    MarketDataModel.symbol == symbol,
                    MarketDataModel.interval == interval
                )
            )
            
            if start_time:
                query = query.where(MarketDataModel.timestamp >= start_time)
            
            if end_time:
                query = query.where(MarketDataModel.timestamp <= end_time)
            
            return session.execute(query).scalar_one()
        finally:
            if close_session and session:
                session.close()
    
    def get_data_summary(
        self,
        symbol: str,
        interval: str,
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Get summary information about stored data for a symbol and interval.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            session: Database session (optional)
            
        Returns:
            Dictionary with summary information
        """
        close_session = False
        if session is None:
            session = self.database.get_session()
            close_session = True
        
        try:
            # Count total records
            count_query = select(func.count(MarketDataModel.id)).where(
                and_(
                    MarketDataModel.symbol == symbol,
                    MarketDataModel.interval == interval
                )
            )
            total_count = session.execute(count_query).scalar_one()
            
            if total_count == 0:
                return {
                    "symbol": symbol,
                    "interval": interval,
                    "count": 0,
                    "first_timestamp": None,
                    "last_timestamp": None,
                    "duration_days": 0
                }
            
            # Get first and last timestamp
            first_ts_query = (
                select(MarketDataModel.timestamp)
                .where(
                    and_(
                        MarketDataModel.symbol == symbol,
                        MarketDataModel.interval == interval
                    )
                )
                .order_by(MarketDataModel.timestamp.asc())
                .limit(1)
            )
            
            last_ts_query = (
                select(MarketDataModel.timestamp)
                .where(
                    and_(
                        MarketDataModel.symbol == symbol,
                        MarketDataModel.interval == interval
                    )
                )
                .order_by(MarketDataModel.timestamp.desc())
                .limit(1)
            )
            
            first_ts = session.execute(first_ts_query).scalar_one()
            last_ts = session.execute(last_ts_query).scalar_one()
            
            # Calculate duration in days
            duration_days = (last_ts - first_ts).total_seconds() / (60 * 60 * 24)
            
            return {
                "symbol": symbol,
                "interval": interval,
                "count": total_count,
                "first_timestamp": first_ts,
                "last_timestamp": last_ts,
                "duration_days": duration_days
            }
        finally:
            if close_session and session:
                session.close() 