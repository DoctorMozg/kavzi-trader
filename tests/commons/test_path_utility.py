"""
Tests for the path utility functions.

This module contains tests for the path utility functions used for handling file paths.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from kavzi_trader.commons.path_utility import ensure_directory_exists


class TestPathUtility:
    """Tests for the path utility functions."""

    @patch("kavzi_trader.commons.path_utility.Path.mkdir")
    def test_ensure_directory_exists(self, mock_mkdir: MagicMock) -> None:
        """Test ensuring a directory exists."""
        # Setup
        path = Path("./test_dir")

        # Execute
        result = ensure_directory_exists(path)

        # Assert
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        assert result == path
