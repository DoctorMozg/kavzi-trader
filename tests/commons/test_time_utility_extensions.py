"""
Tests for the time utility extensions.

This module contains tests for the time utility functions added for
historical data operations.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from kavzi_trader.commons.time_utility import parse_date_range, parse_date_string


class TestTimeUtilityExtensions:
    """Tests for the time utility extensions."""

    @patch("src.commons.time_utility.dateparser.parse")
    def test_parse_date_string(self, mock_parse: MagicMock) -> None:
        """Test parsing a date string."""
        # Setup
        mock_parse.return_value = datetime(2023, 1, 1, tzinfo=UTC)
        date_str = "2023-01-01"

        # Execute
        result = parse_date_string(date_str)

        # Assert
        mock_parse.assert_called_once()
        assert result == datetime(2023, 1, 1, tzinfo=UTC)

    @patch("src.commons.time_utility.dateparser.parse")
    def test_parse_date_string_error(self, mock_parse: MagicMock) -> None:
        """Test error handling when parsing an invalid date string."""
        # Setup
        mock_parse.return_value = None
        date_str = "invalid-date"

        # Execute and Assert
        with pytest.raises(ValueError) as excinfo:
            parse_date_string(date_str)

        assert "Could not parse date" in str(excinfo.value)

    @patch("src.commons.time_utility.parse_date_string")
    def test_parse_date_range(self, mock_parse_date_string: MagicMock) -> None:
        """Test parsing a date range."""
        # Setup
        start_date = "2023-01-01"
        end_date = "2023-01-31"

        mock_parse_date_string.side_effect = [
            datetime(2023, 1, 1, tzinfo=UTC),
            datetime(2023, 1, 31, tzinfo=UTC),
        ]

        # Execute
        start_time, end_time = parse_date_range(start_date, end_date)

        # Assert
        assert mock_parse_date_string.call_count == 2
        assert start_time == datetime(2023, 1, 1, tzinfo=UTC)
        assert end_time == datetime(2023, 1, 31, tzinfo=UTC)

    @patch("src.commons.time_utility.parse_date_string")
    def test_parse_date_range_no_end_date(
        self,
        mock_parse_date_string: MagicMock,
    ) -> None:
        """Test parsing a date range with no end date."""
        # Setup
        start_date = "2023-01-01"

        mock_parse_date_string.return_value = datetime(2023, 1, 1, tzinfo=UTC)

        # Execute
        start_time, end_time = parse_date_range(start_date)

        # Assert
        mock_parse_date_string.assert_called_once_with(start_date)
        assert start_time == datetime(2023, 1, 1, tzinfo=UTC)
        assert end_time is None
