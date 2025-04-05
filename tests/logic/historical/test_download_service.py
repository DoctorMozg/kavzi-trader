"""
Tests for the HistoricalDownloadService.

This module contains tests for the HistoricalDownloadService class,
which is responsible for downloading historical market data.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import click
import pytest

from kavzi_trader.api.binance.historical.batch import (
    DownloadBatchConfigSchema,
    SymbolicDownloadBatchConfigSchema,
)
from kavzi_trader.logic.historical.download_service import HistoricalDownloadService


class TestHistoricalDownloadService:
    """Tests for the HistoricalDownloadService class."""

    @pytest.mark.asyncio()
    async def test_download_klines(
        self,
        mock_binance_client: MagicMock,
    ) -> None:
        """Test downloading klines data."""
        # Setup
        mock_db_session = MagicMock()
        service = HistoricalDownloadService(mock_binance_client, mock_db_session)

        # Setup AsyncMock for the download_klines method
        mock_binance_client.download_klines = AsyncMock()

        symbol = "BTCUSDT"
        interval = "1h"
        start_time = datetime(2023, 1, 1, tzinfo=UTC)
        end_time = datetime(2023, 1, 2, tzinfo=UTC)
        batch_size = 1000
        max_workers = 4

        # Create config
        config = SymbolicDownloadBatchConfigSchema(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size,
            max_workers=max_workers,
        )

        # Execute
        result = await service.download_klines(config=config)

        # Assert
        mock_binance_client.download_klines.assert_called_once_with(config=config)
        assert result == mock_binance_client.download_klines.return_value

    @pytest.mark.asyncio()
    async def test_download_trades(
        self,
        mock_binance_client: MagicMock,
    ) -> None:
        """Test downloading trades data."""
        # Setup
        mock_db_session = MagicMock()
        service = HistoricalDownloadService(mock_binance_client, mock_db_session)

        # Setup AsyncMock for the download_trades method
        mock_binance_client.download_trades = AsyncMock()

        symbol = "BTCUSDT"
        start_time = datetime(2023, 1, 1, tzinfo=UTC)
        end_time = datetime(2023, 1, 2, tzinfo=UTC)
        max_workers = 4

        # Create config
        config = SymbolicDownloadBatchConfigSchema(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            max_workers=max_workers,
        )

        # Execute
        result = await service.download_trades(config=config)

        # Assert
        mock_binance_client.download_trades.assert_called_once_with(config=config)
        assert result == mock_binance_client.download_trades.return_value

    @pytest.mark.asyncio()
    async def test_download_multiple_symbols(
        self,
        mock_binance_client: MagicMock,
    ) -> None:
        """Test downloading data for multiple symbols."""
        # Setup
        mock_db_session = MagicMock()
        service = HistoricalDownloadService(mock_binance_client, mock_db_session)

        # Setup AsyncMock for the download_multiple_symbols method
        mock_binance_client.download_multiple_symbols = AsyncMock()

        # Also mock download_klines to prevent internal calls
        service.download_klines = AsyncMock()  # type: ignore

        symbols = ["BTCUSDT", "ETHUSDT"]
        interval = "1h"
        start_time = datetime(2023, 1, 1, tzinfo=UTC)
        end_time = datetime(2023, 1, 2, tzinfo=UTC)
        batch_size = 1000
        max_workers = 4

        # Create config
        base_config = DownloadBatchConfigSchema(
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size,
            max_workers=max_workers,
        )

        # Setup expected return value
        service.download_klines.return_value = [MagicMock()] * 100

        # Execute
        result = await service.download_multiple_symbols(
            symbols=symbols,
            base_config=base_config,
        )

        # Assert
        # Verify download_klines was called for each symbol
        assert service.download_klines.call_count == 2

        # Verify the symbols matches what we provided
        for symbol in symbols:
            assert symbol in result

        # The result should have True values for each symbol
        assert all(value for value in result.values())

    @pytest.mark.asyncio()
    async def test_download_all_symbols(
        self,
        mock_binance_client: MagicMock,
    ) -> None:
        """Test downloading data for all available symbols."""
        # Setup
        mock_db_session = MagicMock()
        service = HistoricalDownloadService(mock_binance_client, mock_db_session)

        # Setup AsyncMock for the methods
        mock_binance_client.get_filtered_symbols = AsyncMock(
            return_value=["BTCUSDT", "ETHUSDT"],
        )

        # Also mock download_klines to prevent internal calls
        service.download_klines = AsyncMock()  # type: ignore
        service.download_klines.return_value = [MagicMock()] * 100

        interval = "1h"
        start_time = datetime(2023, 1, 1, tzinfo=UTC)
        end_time = datetime(2023, 1, 2, tzinfo=UTC)
        quote_asset = "USDT"
        min_volume = 1000000
        batch_size = 1000
        max_workers = 4

        # Create config
        base_config = DownloadBatchConfigSchema(
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size,
            max_workers=max_workers,
        )

        # Execute
        result = await service.download_all_symbols(
            base_config=base_config,
            quote_asset=quote_asset,
            min_volume=min_volume,
        )

        # Assert
        # Verify get_filtered_symbols was called with correct parameters
        mock_binance_client.get_filtered_symbols.assert_called_once_with(
            quote_asset=quote_asset,
            min_volume=min_volume,
        )

        # Verify download_klines was called for each symbol
        assert service.download_klines.call_count == 2

        # The result should have the symbols as keys
        assert "BTCUSDT" in result
        assert "ETHUSDT" in result

        # The result should have True values for each symbol
        assert all(value for value in result.values())

    async def test_download_klines_error_handling(
        self,
        mock_binance_client: MagicMock,
    ) -> None:
        """Test error handling when downloading klines data."""
        # Setup
        mock_db_session = MagicMock()
        service = HistoricalDownloadService(mock_binance_client, mock_db_session)
        mock_binance_client.download_klines.side_effect = Exception("Test error")

        # Create config
        config = SymbolicDownloadBatchConfigSchema(
            symbol="BTCUSDT",
            interval="1h",
            start_time=datetime(2023, 1, 1, tzinfo=UTC),
            end_time=datetime(2023, 1, 2, tzinfo=UTC),
        )

        # Execute and Assert
        with pytest.raises(click.ClickException):
            await service.download_klines(config=config)

        # Verify the error was logged
        mock_binance_client.download_klines.assert_called_once()
