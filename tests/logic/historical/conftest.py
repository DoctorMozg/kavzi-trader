"""
Fixtures for historical logic tests.

This module provides fixtures for testing historical data logic components.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kavzi_trader.api.binance.historical.client import BinanceHistoricalDataClient


@pytest.fixture()
def mock_binance_client() -> MagicMock:
    """Create a mock BinanceHistoricalDataClient."""
    client = MagicMock(spec=BinanceHistoricalDataClient)

    # Setup common return values
    client.download_klines.return_value = [MagicMock()] * 100
    client.download_trades.return_value = [MagicMock()] * 200
    client.download_multiple_symbols.return_value = ["BTCUSDT", "ETHUSDT"]
    client.download_all_symbols.return_value = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    return client


@pytest.fixture()
def sample_output_path() -> Path:
    """Create a sample output path for testing."""
    return Path("./test_data")
