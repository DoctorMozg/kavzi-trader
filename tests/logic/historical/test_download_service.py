"""
Tests for the HistoricalDownloadService.

This module contains tests for the HistoricalDownloadService class,
which is responsible for downloading historical market data.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import click
import pytest

from src.logic.historical.download_service import HistoricalDownloadService


class TestHistoricalDownloadService:
    """Tests for the HistoricalDownloadService class."""

    def test_download_klines(
        self,
        mock_binance_client: MagicMock,
        sample_output_path: Path,
    ) -> None:
        """Test downloading klines data."""
        # Setup
        service = HistoricalDownloadService(mock_binance_client)

        symbol = "BTCUSDT"
        interval = "1h"
        start_time = datetime(2023, 1, 1, tzinfo=UTC)
        end_time = datetime(2023, 1, 2, tzinfo=UTC)
        batch_size = 1000
        max_workers = 4
        save_progress = True

        # Execute
        result = service.download_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size,
            max_workers=max_workers,
            output_dir=sample_output_path,
            save_progress=save_progress,
        )

        # Assert
        mock_binance_client.download_klines.assert_called_once_with(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size,
            max_workers=max_workers,
            output_dir=sample_output_path,
            save_progress=save_progress,
        )
        assert result == mock_binance_client.download_klines.return_value

    def test_download_trades(
        self,
        mock_binance_client: MagicMock,
        sample_output_path: Path,
    ) -> None:
        """Test downloading trades data."""
        # Setup
        service = HistoricalDownloadService(mock_binance_client)

        symbol = "BTCUSDT"
        start_time = datetime(2023, 1, 1, tzinfo=UTC)
        end_time = datetime(2023, 1, 2, tzinfo=UTC)
        max_workers = 4
        save_progress = True

        # Execute
        result = service.download_trades(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            max_workers=max_workers,
            output_dir=sample_output_path,
            save_progress=save_progress,
        )

        # Assert
        mock_binance_client.download_trades.assert_called_once_with(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            max_workers=max_workers,
            output_dir=sample_output_path,
            save_progress=save_progress,
        )
        assert result == mock_binance_client.download_trades.return_value

    def test_download_multiple_symbols(
        self,
        mock_binance_client: MagicMock,
        sample_output_path: Path,
    ) -> None:
        """Test downloading data for multiple symbols."""
        # Setup
        service = HistoricalDownloadService(mock_binance_client)

        symbols = ["BTCUSDT", "ETHUSDT"]
        interval = "1h"
        start_time = datetime(2023, 1, 1, tzinfo=UTC)
        end_time = datetime(2023, 1, 2, tzinfo=UTC)
        batch_size = 1000
        max_workers = 4

        # Execute
        result = service.download_multiple_symbols(
            symbols=symbols,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size,
            max_workers=max_workers,
            output_dir=sample_output_path,
        )

        # Assert
        # Check that the download_multiple_symbols method
        # was called with the correct config
        mock_binance_client.download_multiple_symbols.assert_called_once()

        # Extract the config argument from the call
        call_args = mock_binance_client.download_multiple_symbols.call_args[1]
        assert "config" in call_args
        assert "symbols" in call_args
        assert call_args["symbols"] == symbols

        # Verify the config has the correct values
        config = call_args["config"]
        assert config.interval == interval
        assert config.start_time == start_time
        assert config.batch_size == batch_size
        assert config.max_workers == max_workers
        assert config.output_dir == sample_output_path

        assert result == mock_binance_client.download_multiple_symbols.return_value

    def test_download_all_symbols(
        self,
        mock_binance_client: MagicMock,
        sample_output_path: Path,
    ) -> None:
        """Test downloading data for all available symbols."""
        # Setup
        service = HistoricalDownloadService(mock_binance_client)

        interval = "1h"
        start_time = datetime(2023, 1, 1, tzinfo=UTC)
        end_time = datetime(2023, 1, 2, tzinfo=UTC)
        quote_asset = "USDT"
        min_volume = 1000000
        batch_size = 1000
        max_workers = 4

        # Execute
        result = service.download_all_symbols(
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            quote_asset=quote_asset,
            min_volume=min_volume,
            batch_size=batch_size,
            max_workers=max_workers,
            output_dir=sample_output_path,
        )

        # Assert
        mock_binance_client.download_all_symbols.assert_called_once_with(
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            quote_asset=quote_asset,
            min_volume=min_volume,
            batch_size=batch_size,
            max_workers=max_workers,
            output_dir=sample_output_path,
        )
        assert result == mock_binance_client.download_all_symbols.return_value

    def test_download_klines_error_handling(
        self,
        mock_binance_client: MagicMock,
        sample_output_path: Path,
    ) -> None:
        """Test error handling when downloading klines data."""
        # Setup
        service = HistoricalDownloadService(mock_binance_client)
        mock_binance_client.download_klines.side_effect = Exception("Test error")

        # Execute and Assert
        with pytest.raises(click.ClickException):
            service.download_klines(
                symbol="BTCUSDT",
                interval="1h",
                start_time=datetime(2023, 1, 1, tzinfo=UTC),
                output_dir=sample_output_path,
            )

        # Verify the error was logged
        mock_binance_client.download_klines.assert_called_once()
