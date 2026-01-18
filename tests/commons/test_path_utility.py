"""
Tests for the path utility functions.

This module contains tests for the path utility functions used for handling file paths.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from kavzi_trader.commons.path_utility import (
    create_output_path,
    ensure_directory_exists,
)


class TestPathUtility:
    """Tests for the path utility functions."""

    def test_create_output_path_with_output_dir(self) -> None:
        """Test creating an output path with a provided output directory."""
        # Setup
        output_dir = "./test_output"

        # Execute
        result = create_output_path(output_dir)

        # Assert
        assert result == Path("./test_output")

    def test_create_output_path_with_default(self) -> None:
        """Test creating an output path with the default directory."""
        # Execute
        result = create_output_path()

        # Assert
        assert result == Path("./data")

    def test_create_output_path_with_custom_default(self) -> None:
        """Test creating an output path with a custom default directory."""
        # Execute
        result = create_output_path(default_dir="./custom_default")

        # Assert
        assert result == Path("./custom_default")

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
