"""
Trade data repository for database operations.

This module provides repository classes for trade data operations,
implementing the repository pattern to abstract database access.
"""

import logging
from datetime import datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func, text

from src.api.common.models import TradeSchema
from src.data.storage.models.market_data import TradeDataModel
from src.data.storage.repos.base_repo import BaseRepository

logger = logging.getLogger(__name__)


class TradeDataRepository(BaseRepository[TradeDataModel]):
    """
    Repository for trade data operations.

    Handles database operations for trade data.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize a trade data repository.

        Args:
            session: SQLAlchemy async session
        """
        super().__init__(session, TradeDataModel)

    async def get_by_symbol_trade_id(
        self,
        symbol: str,
        trade_id: int,
    ) -> TradeDataModel | None:
        """
        Get trade data by symbol and trade ID.

        Args:
            symbol: Trading pair symbol
            trade_id: Trade ID

        Returns:
            Trade data model if found, None otherwise
        """
        result = await self.session.execute(
            select(TradeDataModel).where(
                TradeDataModel.symbol == symbol,
                TradeDataModel.trade_id == trade_id,
            ),
        )
        return cast(TradeDataModel | None, result.scalars().first())

    async def get_by_symbol_time_range(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[TradeDataModel]:
        """
        Get trades within a time range.

        Args:
            symbol: Trading pair symbol
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of trade data models
        """
        result = await self.session.execute(
            select(TradeDataModel)
            .where(
                TradeDataModel.symbol == symbol,
                TradeDataModel.timestamp >= start_time,
                TradeDataModel.timestamp <= end_time,
            )
            .order_by(TradeDataModel.timestamp),
        )
        return cast(list[TradeDataModel], result.scalars().all())

    async def save_trade(
        self,
        trade: TradeSchema,
        symbol: str,
    ) -> TradeDataModel:
        """
        Save a single trade to the database.

        Args:
            trade: Trade data
            symbol: Trading pair symbol

        Returns:
            Saved trade data model
        """
        # Check if record already exists
        existing = await self.get_by_symbol_trade_id(symbol=symbol, trade_id=trade.id)

        if existing:
            # Trade data should be immutable, but we'll update it for completeness
            existing.price = trade.price
            existing.quantity = trade.qty
            existing.quote_quantity = trade.quote_qty
            existing.timestamp = trade.time
            existing.is_buyer_maker = trade.is_buyer_maker
            existing.is_best_match = trade.is_best_match
            existing.buyer_order_id = trade.buyer_order_id
            existing.seller_order_id = trade.seller_order_id
            return existing

        # Create new record
        model = TradeDataModel(
            symbol=symbol,
            trade_id=trade.id,
            price=trade.price,
            quantity=trade.qty,
            quote_quantity=trade.quote_qty,
            timestamp=trade.time,
            is_buyer_maker=trade.is_buyer_maker,
            is_best_match=trade.is_best_match,
            buyer_order_id=trade.buyer_order_id,
            seller_order_id=trade.seller_order_id,
        )
        return await self.add(model)

    async def save_trades(
        self,
        trades: list[TradeSchema],
        symbol: str,
        batch_size: int = 1000,
    ) -> list[TradeDataModel]:
        """
        Save multiple trades to the database.

        Args:
            trades: List of trade data
            symbol: Trading pair symbol
            batch_size: Size of each batch for saving

        Returns:
            List of saved trade data models
        """
        if not trades:
            logger.warning("No trades to save")
            return []

        logger.info("Saving %d trades to database", len(trades))

        result: list[TradeDataModel] = []

        # Save in batches
        for i in range(0, len(trades), batch_size):
            batch = trades[i : i + batch_size]
            models = []

            for trade in batch:
                model = TradeDataModel(
                    symbol=symbol,
                    trade_id=trade.id,
                    price=trade.price,
                    quantity=trade.qty,
                    quote_quantity=trade.quote_qty,
                    timestamp=trade.time,
                    is_buyer_maker=trade.is_buyer_maker,
                    is_best_match=trade.is_best_match,
                    buyer_order_id=trade.buyer_order_id,
                    seller_order_id=trade.seller_order_id,
                )
                models.append(model)

            saved_models = await self.add_all(models)
            result.extend(saved_models)

            logger.info(
                "Saved batch %d/%d with %d trades",
                (i // batch_size) + 1,
                (len(trades) + batch_size - 1) // batch_size,
                len(batch),
            )

        return result

    async def get_latest_trade_id(self, symbol: str) -> int | None:
        """
        Get the latest trade ID for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest trade ID if found, None otherwise
        """
        result = await self.session.execute(
            select(func.max(TradeDataModel.trade_id)).where(
                TradeDataModel.symbol == symbol,
            ),
        )
        return cast(int | None, result.scalar_one_or_none())

    async def get_latest_timestamp(self, symbol: str) -> datetime | None:
        """
        Get the latest timestamp for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest timestamp if found, None otherwise
        """
        result = await self.session.execute(
            select(func.max(TradeDataModel.timestamp)).where(
                TradeDataModel.symbol == symbol,
            ),
        )
        return cast(datetime | None, result.scalar_one_or_none())

    async def get_symbols(self) -> list[str]:
        """
        Get all symbols with trade data.

        Returns:
            List of unique symbols
        """
        query = select(TradeDataModel.symbol).distinct()
        result = await self.session.execute(query)
        return cast(list[str], result.scalars().all())

    async def get_trade_count(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int | None:
        """
        Get the count of trade data records, optionally filtered.

        Args:
            symbol: Trading pair symbol
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Count of records
        """
        query = select(func.count()).select_from(TradeDataModel)
        if symbol:
            query = query.where(TradeDataModel.symbol == symbol)
        if start_time:
            query = query.where(TradeDataModel.timestamp >= start_time)
        if end_time:
            query = query.where(TradeDataModel.timestamp <= end_time)

        result = await self.session.execute(query)
        return cast(int | None, result.scalar())

    async def get_last_timestamp(
        self,
        symbol: str,
    ) -> datetime | None:
        """
        Get the latest timestamp for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest timestamp if records exist, None otherwise
        """
        query = select(func.max(TradeDataModel.timestamp)).where(
            TradeDataModel.symbol == symbol,
        )
        result = await self.session.execute(query)
        timestamp = result.scalar()
        return cast(datetime | None, timestamp)

    async def get_data_range(
        self,
        symbol: str,
    ) -> tuple[datetime | None, datetime | None]:
        """
        Get the range of timestamps for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Tuple of (min_timestamp, max_timestamp), values may be None if no data
        """
        min_query = select(func.min(TradeDataModel.timestamp)).where(
            TradeDataModel.symbol == symbol,
        )
        max_query = select(func.max(TradeDataModel.timestamp)).where(
            TradeDataModel.symbol == symbol,
        )

        min_result = await self.session.execute(min_query)
        max_result = await self.session.execute(max_query)

        min_timestamp = min_result.scalar()
        max_timestamp = max_result.scalar()

        return cast(datetime | None, min_timestamp), cast(
            datetime | None,
            max_timestamp,
        )

    async def delete_by_symbol(
        self,
        symbol: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """
        Delete trade data for a symbol, optionally within a time range.

        Args:
            symbol: Trading pair symbol
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Number of records deleted
        """
        query = (
            text(
                """
                DELETE FROM trade_data
                WHERE symbol = :symbol
                """,
            )
            .bindparams(symbol=symbol)
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
