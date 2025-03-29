"""
Tests for the HistoricalClientFactory.

This module contains tests for the HistoricalClientFactory class,
which is responsible for creating and configuring historical data clients.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.logic.historical.client_factory import HistoricalClientFactory


class TestHistoricalClientFactory:
    """Tests for the HistoricalClientFactory class."""

    @patch("src.logic.historical.client_factory.BinanceHistoricalDataClient")
    def test_create_binance_client(self, mock_client_class: MagicMock) -> None:
        """Test creating a Binance historical data client."""
        # Setup
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        api_key = "test_api_key"
        api_secret = "test_api_secret"  # noqa: S105 - This is a test value, not a real secret
        max_workers = 4
        batch_size = 1000
        output_dir = Path("./test_data")

        # Execute
        client = HistoricalClientFactory.create_binance_client(
            api_key=api_key,
            api_secret=api_secret,
            max_workers=max_workers,
            batch_size=batch_size,
            output_dir=output_dir,
        )

        # Assert
        mock_client_class.assert_called_once_with(
            api_key=api_key,
            api_secret=api_secret,
            max_workers=max_workers,
            batch_size=batch_size,
            output_dir=output_dir,
        )
        assert client == mock_client_instance
