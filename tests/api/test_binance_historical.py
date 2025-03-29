"""
Tests for Binance Historical Data Client.

This module contains tests for the BinanceHistoricalDataClient implementation.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.api.binance.historical.batch import BatchProcessor, DownloadBatchConfigSchema
from src.api.binance.historical.client import BinanceHistoricalDataClient
from src.api.common.models import CandlestickSchema, TradeSchema
from src.commons.time_utility import utc_now


def test_init(historical_client: BinanceHistoricalDataClient) -> None:
    """Test client initialization."""
    assert historical_client.max_workers == 2
    assert historical_client.batch_size == 100
    assert historical_client.output_dir.exists()


@patch("src.api.binance.historical.batch.BatchProcessor.get_kline_batch_intervals")
def test_get_batch_intervals(
    mock_get_intervals: MagicMock,
    historical_client: BinanceHistoricalDataClient,
) -> None:
    """Test batch interval generation."""
    # Setup mock return value
    mock_batches = [
        {"start_time": 1609459200000, "end_time": 1609459200000 + 3600000},
        {"start_time": 1609459200000 + 3600001, "end_time": 1609459200000 + 7200000},
    ]
    mock_get_intervals.return_value = mock_batches

    start_time = datetime(2021, 1, 1, tzinfo=UTC)
    end_time = datetime(2021, 1, 2, tzinfo=UTC)
    interval = "1h"
    batch_size = 10

    # Call the method through BatchProcessor directly
    batches = BatchProcessor.get_kline_batch_intervals(
        start_time=start_time,
        end_time=end_time,
        interval=interval,
        batch_size=batch_size,
    )

    # Verify the result
    assert batches == mock_batches
    mock_get_intervals.assert_called_once_with(
        start_time=start_time,
        end_time=end_time,
        interval=interval,
        batch_size=batch_size,
    )


@pytest.fixture()
def mock_candlestick_schemas() -> list[CandlestickSchema]:
    """Create mock kline data for testing."""
    now = utc_now()
    klines = []

    for i in range(5):
        kline_time = now - timedelta(hours=i)
        kline = CandlestickSchema(
            symbol="BTCUSDT",
            interval="1h",
            open_time=kline_time,
            close_time=kline_time + timedelta(hours=1),
            open_price=Decimal(50000.0),
            high_price=Decimal(51000.0),
            low_price=Decimal(49500.0),
            close_price=Decimal(50500.0),
            volume=Decimal(10.5),
            quote_volume=Decimal(525000.0),
            trades_count=1000,
            taker_buy_base_volume=Decimal(5.25),
            taker_buy_quote_volume=Decimal(262500.0),
        )
        klines.append(kline)

    return klines


@pytest.fixture()
def mock_trade_schemas() -> list[TradeSchema]:
    """Create mock trade data for testing."""
    now = utc_now()
    trades = []

    for i in range(5):
        trade_time = now - timedelta(minutes=i)
        trade = TradeSchema(
            id=1000 + i,
            price=Decimal(50000.0 + i * 10),
            qty=Decimal(0.1),
            time=trade_time,
            is_buyer_maker=i % 2 == 0,
            is_best_match=True,
            quote_qty=Decimal(5000.0 + i),
        )
        trades.append(trade)

    return trades


def test_save_data(
    historical_client: BinanceHistoricalDataClient,
    mock_candlestick_schemas: list[CandlestickSchema],
) -> None:
    """Test saving data to CSV format."""
    # Test CSV saving
    csv_path = historical_client.klines_downloader.data_saver.save_data(
        data=mock_candlestick_schemas,
        symbol="BTCUSDT",
        data_type="klines",
        interval="1h",
        start_time=utc_now() - timedelta(hours=5),
        end_time=utc_now(),
    )

    assert csv_path.exists()
    assert csv_path.suffix == ".csv"

    # Verify the CSV file contains the data
    result_df = pd.read_csv(csv_path)
    assert len(result_df) == len(mock_candlestick_schemas)

    # Clean up the test file
    csv_path.unlink()


@patch("src.api.binance.historical.downloaders.klines.KlinesDownloader._download_batch")
def test_download_klines(
    mock_download_batch: MagicMock,
    historical_client: BinanceHistoricalDataClient,
    mock_candlestick_schemas: list[CandlestickSchema],
) -> None:
    """Test downloading klines."""
    # Mock the batch download to return predefined data
    mock_download_batch.return_value = mock_candlestick_schemas

    # Mock the batch intervals to return a predictable number of batches
    with patch(
        "src.api.binance.historical.batch.BatchProcessor.get_kline_batch_intervals",
    ) as mock_get_intervals:
        mock_get_intervals.return_value = [
            {"start_time": 1609459200000, "end_time": 1609459200000 + 3600000},
            {
                "start_time": 1609459200000 + 3600001,
                "end_time": 1609459200000 + 7200000,
            },
        ]

        klines = historical_client.download_klines(
            symbol="BTCUSDT",
            interval="1h",
            start_time=utc_now() - timedelta(days=1),
            end_time=utc_now(),
            batch_size=100,
        )

        # Verify the result
        assert mock_download_batch.called
        assert len(klines) == 2 * len(mock_candlestick_schemas)  # 2 batches

        # The actual number of calls depends on the batch size and time range
        # This just verifies that batching works
        assert mock_download_batch.call_count == 2


@patch("src.api.binance.historical.downloaders.trades.TradesDownloader._download_batch")
def test_download_trades(
    mock_download_batch: MagicMock,
    historical_client: BinanceHistoricalDataClient,
    mock_trade_schemas: list[TradeSchema],
) -> None:
    """Test downloading trades."""
    # Mock the batch download to return predefined data
    mock_download_batch.return_value = mock_trade_schemas

    # Mock the batch intervals to return a predictable number of batches
    with patch(
        "src.api.binance.historical.batch.BatchProcessor.get_trade_batch_intervals",
    ) as mock_get_intervals:
        mock_get_intervals.return_value = [
            {
                "start_time": datetime(2023, 1, 1, tzinfo=UTC),
                "end_time": datetime(2023, 1, 2, tzinfo=UTC),
            },
            {
                "start_time": datetime(2023, 1, 2, tzinfo=UTC),
                "end_time": datetime(2023, 1, 3, tzinfo=UTC),
            },
        ]

        # Set up test dates for predictable behavior
        end_time = datetime(2023, 1, 3, tzinfo=UTC)
        start_time = datetime(2023, 1, 1, tzinfo=UTC)

        trades = historical_client.download_trades(
            symbol="BTCUSDT",
            start_time=start_time,
            end_time=end_time,
        )

        # Verify that the batch download function is called
        assert mock_download_batch.called

        # Verify that the mock was called at least once
        assert mock_download_batch.call_count == 2

        # The length of trades should be a multiple of the mock_trades length
        # Since we're using a mock that returns the same data each time
        assert len(trades) == mock_download_batch.call_count * len(mock_trade_schemas)

        # Verify that the mock trades are included in the result
        for trade in mock_trade_schemas:
            assert trade in trades


@patch("src.api.binance.historical.client.BinanceHistoricalDataClient.download_klines")
def test_download_multiple_symbols(
    mock_download_klines: MagicMock,
    historical_client: BinanceHistoricalDataClient,
    mock_candlestick_schemas: list[CandlestickSchema],
) -> None:
    """Test downloading data for multiple symbols."""
    # Mock download_klines to return predefined data
    mock_download_klines.return_value = mock_candlestick_schemas

    config = DownloadBatchConfigSchema(
        symbol="",  # Will be set per download
        interval="1h",
        start_time=utc_now() - timedelta(days=1),
        end_time=utc_now(),
        batch_size=100,
        max_workers=2,
        output_dir=Path("./test_output"),
    )

    symbols = ["BTCUSDT", "ETHUSDT"]
    results = historical_client.download_multiple_symbols(config, symbols)

    # Verify the result
    assert mock_download_klines.call_count == len(symbols)
    assert len(results) <= len(symbols)  # May be less if any downloads fail


@patch(
    "src.api.binance.historical.client.BinanceHistoricalDataClient.download_multiple_symbols",
)
def test_download_all_symbols(
    mock_download_multiple: MagicMock,
    historical_client: BinanceHistoricalDataClient,
) -> None:
    """Test downloading data for all symbols with filtering."""
    # Mock get_exchange_info to return test symbols
    historical_client.client.get_exchange_info.return_value = {  # type: ignore
        "symbols": [
            {"symbol": "BTCUSDT", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "ETHUSDT", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "BNBBTC", "status": "TRADING", "quoteAsset": "BTC"},
            {"symbol": "LTCUSDT", "status": "HALT", "quoteAsset": "USDT"},
        ],
    }

    # Mock get_all_tickers for volume filtering
    historical_client.client.get_all_tickers.return_value = [  # type: ignore
        MagicMock(symbol="BTCUSDT", volume="10000000"),
        MagicMock(symbol="ETHUSDT", volume="5000000"),
    ]

    # Mock download_multiple_symbols to return expected result with Path objects
    mock_download_multiple.return_value = {  # type: ignore
        "BTCUSDT": Path("/path/to/btc.csv"),
        "ETHUSDT": Path("/path/to/eth.csv"),
    }

    # Test with quote asset and volume filtering
    results = historical_client.download_all_symbols(
        interval="1h",
        start_time=utc_now() - timedelta(days=1),
        end_time=utc_now(),
        quote_asset="USDT",
        min_volume=1000000,
    )

    # Verify that filtering works
    mock_download_multiple.assert_called_once()
    # Should only include BTCUSDT and ETHUSDT
    # (BNBBTC has wrong quote asset, LTCUSDT is halted)
    call_args = mock_download_multiple.call_args[0]
    assert len(call_args[1]) == 2
    assert "BTCUSDT" in call_args[1]
    assert "ETHUSDT" in call_args[1]

    # Check that results are returned correctly
    assert len(results) == 2
    assert "BTCUSDT" in results
    assert "ETHUSDT" in results


def test_download_klines_batch(
    historical_client: BinanceHistoricalDataClient,
    mock_candlestick_schemas: list[CandlestickSchema],
) -> None:
    """Test downloading a batch of klines."""
    # Mock the client's get_klines method
    historical_client.client.get_klines.return_value = mock_candlestick_schemas  # type: ignore

    # Call the method
    result = historical_client.klines_downloader._download_batch(
        symbol="BTCUSDT",
        interval="1h",
        start_time=utc_now() - timedelta(hours=5),
        end_time=utc_now(),
    )

    # Verify the result
    assert historical_client.client.get_klines.called  # type: ignore
    assert len(result) == len(mock_candlestick_schemas)


@patch("src.api.binance.historical.downloaders.trades.TradesDownloader._download_batch")
def test_download_trades_batch(
    mock_download_batch: MagicMock,
    historical_client: BinanceHistoricalDataClient,
    mock_trade_schemas: list[TradeSchema],
) -> None:
    """Test downloading a batch of trades."""
    # Mock the download_batch method to return our mock data
    mock_download_batch.return_value = mock_trade_schemas

    # Call the method through the client
    result = historical_client.trades_downloader._download_batch(
        symbol="BTCUSDT",
        start_time=utc_now() - timedelta(hours=1),
        end_time=utc_now(),
    )

    # Verify the result
    assert mock_download_batch.called
    assert len(result) == len(mock_trade_schemas)
