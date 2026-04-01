"""
Tests for the time utility extensions.

This module contains tests for the time utility functions added for
historical data operations.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from kavzi_trader.commons.time_utility import parse_date_string


class TestTimeUtilityExtensions:
    """Tests for the time utility extensions."""

    @patch("kavzi_trader.commons.time_utility.dateparser.parse")
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

    @patch("kavzi_trader.commons.time_utility.dateparser.parse")
    def test_parse_date_string_error(self, mock_parse: MagicMock) -> None:
        """Test error handling when parsing an invalid date string."""
        # Setup
        mock_parse.return_value = None
        date_str = "invalid-date"

        # Execute and Assert
        with pytest.raises(ValueError) as excinfo:
            parse_date_string(date_str)

        assert "Could not parse date" in str(excinfo.value)
