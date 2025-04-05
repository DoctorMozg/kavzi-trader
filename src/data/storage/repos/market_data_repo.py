"""
Market data repository for database operations.

This module provides repository classes for market data operations,
implementing the repository pattern to abstract database access.
"""

import logging
from datetime import datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func, text

from src.api.common.models import CandlestickSchema
from src.data.storage.models.market_data import MarketDataModel
from src.data.storage.repos.base_repo import BaseRepository

logger = logging.getLogger(__name__)


class MarketDataRepository(BaseRepository[MarketDataModel]):
    """
    Repository for market data operations.

    Handles database operations for candlestick data.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize a market data repository.

        Args:
            session: SQLAlchemy async session
        """
        super().__init__(session, MarketDataModel)

    async def get_by_symbol_interval_time(
        self,
        symbol: str,
        interval: str,
        timestamp: datetime,
    ) -> MarketDataModel | None:
        """
        Get market data by symbol, interval, and timestamp.

        Args:
            symbol: Trading pair symbol
            interval: Kline interval
            timestamp: Kline timestamp

        Returns:
            Market data model if found, None otherwise
        """
        result = await self.session.execute(
            select(MarketDataModel).where(
                MarketDataModel.symbol == symbol,
                MarketDataModel.interval == interval,
                MarketDataModel.timestamp == timestamp,
            ),
        )
        return cast(MarketDataModel | None, result.scalars().first())

    async def get_by_symbol_interval_time_range(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[MarketDataModel]:
        """
        Get market data within a time range.

        Args:
            symbol: Trading pair symbol
            interval: Kline interval
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of market data models
        """
        result = await self.session.execute(
            select(MarketDataModel)
            .where(
                MarketDataModel.symbol == symbol,
                MarketDataModel.interval == interval,
                MarketDataModel.timestamp >= start_time,
                MarketDataModel.timestamp <= end_time,
            )
            .order_by(MarketDataModel.timestamp),
        )
        return cast(list[MarketDataModel], result.scalars().all())

    async def save_candlestick(
        self,
        candlestick: CandlestickSchema,
        symbol: str,
        interval: str,
    ) -> MarketDataModel:
        """
        Save a single candlestick to the database.

        Args:
            candlestick: Candlestick data
            symbol: Trading pair symbol
            interval: Kline interval

        Returns:
            Saved market data model
        """
        # Check if record already exists
        existing = await self.get_by_symbol_interval_time(
            symbol=symbol,
            interval=interval,
            timestamp=candlestick.open_time,
        )

        if existing:
            # Update existing record
            existing.opened = candlestick.open_price
            existing.high = candlestick.high_price
            existing.low = candlestick.low_price
            existing.closed = candlestick.close_price
            existing.volume = candlestick.volume
            existing.quote_volume = candlestick.quote_volume
            existing.trades = candlestick.trades_count
            existing.taker_buy_base_volume = candlestick.taker_buy_base_volume
            existing.taker_buy_quote_volume = candlestick.taker_buy_quote_volume
            return existing

        # Create new record
        model = MarketDataModel(
            symbol=symbol,
            interval=interval,
            timestamp=candlestick.open_time,
            opened=candlestick.open_price,
            high=candlestick.high_price,
            low=candlestick.low_price,
            closed=candlestick.close_price,
            volume=candlestick.volume,
            quote_volume=candlestick.quote_volume,
            trades=candlestick.trades_count,
            taker_buy_base_volume=candlestick.taker_buy_base_volume,
            taker_buy_quote_volume=candlestick.taker_buy_quote_volume,
        )
        return await self.add(model)

    async def save_candlesticks(
        self,
        candlesticks: list[CandlestickSchema],
        symbol: str,
        interval: str,
        batch_size: int = 1000,
    ) -> list[MarketDataModel]:
        """
        Save multiple candlesticks to the database.

        Args:
            candlesticks: List of candlestick data
            symbol: Trading pair symbol
            interval: Kline interval
            batch_size: Size of each batch for saving

        Returns:
            List of saved market data models
        """
        if not candlesticks:
            logger.warning("No candlesticks to save")
            return []

        logger.info("Saving %d candlesticks to database", len(candlesticks))

        result: list[MarketDataModel] = []

        # Save in batches
        for i in range(0, len(candlesticks), batch_size):
            batch = candlesticks[i : i + batch_size]
            models = []

            for candlestick in batch:
                model = MarketDataModel(
                    symbol=symbol,
                    interval=interval,
                    timestamp=candlestick.open_time,
                    opened=candlestick.open_price,
                    high=candlestick.high_price,
                    low=candlestick.low_price,
                    closed=candlestick.close_price,
                    volume=candlestick.volume,
                    quote_volume=candlestick.quote_volume,
                    trades=candlestick.trades_count,
                    taker_buy_base_volume=candlestick.taker_buy_base_volume,
                    taker_buy_quote_volume=candlestick.taker_buy_quote_volume,
                )
                models.append(model)

            saved_models = await self.add_all(models)
            result.extend(saved_models)

            logger.info(
                "Saved batch %d/%d with %d candlesticks",
                (i // batch_size) + 1,
                (len(candlesticks) + batch_size - 1) // batch_size,
                len(batch),
            )
        # Flush the transaction to ensure data is committed to the database
        await self.session.commit()

        return result

    async def get_latest_timestamp(
        self,
        symbol: str,
        interval: str,
    ) -> datetime | None:
        """
        Get the latest timestamp for a symbol and interval.

        Args:
            symbol: Trading pair symbol
            interval: Kline interval

        Returns:
            Latest timestamp if found, None otherwise
        """
        result = await self.session.execute(
            select(func.max(MarketDataModel.timestamp)).where(
                MarketDataModel.symbol == symbol,
                MarketDataModel.interval == interval,
            ),
        )
        return cast(datetime | None, result.scalar_one_or_none())

    async def get_symbols(self) -> list[str]:
        """
        Get all symbols with market data.

        Returns:
            List of unique symbols
        """
        query = select(MarketDataModel.symbol).distinct()
        result = await self.session.execute(query)
        return cast(list[str], result.scalars().all())

    async def get_intervals(self, symbol: str | None = None) -> list[str]:
        """
        Get all intervals with market data, optionally filtered by symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            List of unique intervals
        """
        query = select(MarketDataModel.interval).distinct()
        if symbol:
            query = query.where(MarketDataModel.symbol == symbol)
        result = await self.session.execute(query)
        return cast(list[str], result.scalars().all())

    async def get_last_timestamp(
        self,
        symbol: str,
        interval: str,
    ) -> datetime | None:
        """
        Get the latest timestamp for a symbol and interval.

        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval

        Returns:
            Latest timestamp if records exist, None otherwise
        """
        query = (
            select(func.max(MarketDataModel.timestamp))
            .where(MarketDataModel.symbol == symbol)
            .where(MarketDataModel.interval == interval)
        )
        result = await self.session.execute(query)
        timestamp = result.scalar()
        return cast(datetime | None, timestamp)

    async def get_data_range(
        self,
        symbol: str,
        interval: str,
    ) -> tuple[datetime | None, datetime | None]:
        """
        Get the range of timestamps for a symbol and interval.

        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval

        Returns:
            Tuple of (min_timestamp, max_timestamp), values may be None if no data
        """
        min_query = (
            select(func.min(MarketDataModel.timestamp))
            .where(MarketDataModel.symbol == symbol)
            .where(MarketDataModel.interval == interval)
        )
        max_query = (
            select(func.max(MarketDataModel.timestamp))
            .where(MarketDataModel.symbol == symbol)
            .where(MarketDataModel.interval == interval)
        )

        min_result = await self.session.execute(min_query)
        max_result = await self.session.execute(max_query)

        min_timestamp = min_result.scalar()
        max_timestamp = max_result.scalar()

        return cast(datetime | None, min_timestamp), cast(
            datetime | None,
            max_timestamp,
        )

    async def get_data_count(
        self,
        symbol: str | None = None,
        interval: str | None = None,
    ) -> int:
        """
        Get the count of market data records, optionally filtered.

        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval

        Returns:
            Count of records
        """
        query = select(func.count()).select_from(MarketDataModel)
        if symbol:
            query = query.where(MarketDataModel.symbol == symbol)
        if interval:
            query = query.where(MarketDataModel.interval == interval)

        result = await self.session.execute(query)
        return cast(int, result.scalar_one())

    async def delete_by_symbol_interval(
        self,
        symbol: str,
        interval: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """
        Delete market data for a symbol and interval, optionally within a time range.

        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Number of records deleted
        """
        query = (
            text(
                """
                DELETE FROM market_data
                WHERE symbol = :symbol
                AND interval = :interval
                """,
            )
            .bindparams(symbol=symbol, interval=interval)
            .execution_options(autocommit=True)
        )

        if start_time:
            query = query.bindparams(start_time=start_time)
            query = text(query.text + " AND timestamp >= :start_time")

        if end_time:
            query = query.bindparams(end_time=end_time)
            query = text(query.text + " AND timestamp <= :end_time")

        result = await self.session.execute(query)
        return cast(int, result.rowcount)
