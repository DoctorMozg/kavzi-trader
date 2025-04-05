"""
Tests for async utility functions.
"""

import asyncio
import time

import pytest

from kavzi_trader.commons.async_utils import to_async, to_sync


def test_to_async_decorator() -> None:
    """Test that the to_async decorator converts a sync function to an async one."""

    # Define a synchronous function
    def sync_function(x: int, y: int) -> int:
        return x + y

    # Apply the decorator
    async_function = to_async(sync_function)

    # Verify it's now an async function
    assert asyncio.iscoroutinefunction(async_function)
    assert not asyncio.iscoroutinefunction(sync_function)

    # Test the function works correctly
    result = asyncio.run(async_function(5, 3))
    assert result == 8


def test_to_async_with_io_operation() -> None:
    """Test that the to_async decorator works with I/O operations."""

    # Define a synchronous function that simulates I/O
    def slow_io_operation(duration: float) -> float:
        time.sleep(duration)
        return duration

    # Apply the decorator
    async_io_operation = to_async(slow_io_operation)

    # Define a wrapper coroutine to make asyncio.run happy
    async def run_async_operation() -> float:
        return await async_io_operation(0.1)

    # Test the function works correctly
    start_time = time.time()
    result: float = asyncio.run(run_async_operation())
    elapsed = time.time() - start_time

    assert result == 0.1
    assert elapsed >= 0.1  # Ensure it actually waited


def test_to_sync_decorator() -> None:
    """Test that the to_sync decorator converts an async function to a sync one."""

    # Define an asynchronous function
    async def async_function(x: int, y: int) -> int:
        await asyncio.sleep(0.01)  # Small delay to ensure it's truly async
        return x + y

    # Apply the decorator
    sync_function = to_sync(async_function)

    # Verify it's now a sync function
    assert not asyncio.iscoroutinefunction(sync_function)
    assert asyncio.iscoroutinefunction(async_function)

    # Test the function works correctly
    result = sync_function(5, 3)
    assert result == 8


def test_to_sync_with_io_operation() -> None:
    """Test that the to_sync decorator works with async I/O operations."""

    # Define an asynchronous function that simulates I/O
    async def async_io_operation(duration: float) -> float:
        await asyncio.sleep(duration)
        return duration

    # Apply the decorator
    sync_io_operation = to_sync(async_io_operation)

    # Test the function works correctly
    start_time = time.time()
    result = sync_io_operation(0.1)
    elapsed = time.time() - start_time

    assert result == 0.1
    assert elapsed >= 0.1  # Ensure it actually waited


def test_to_sync_error_handling() -> None:
    """Test that the to_sync decorator properly handles errors in the async function."""

    # Define an async function that raises an exception
    async def async_error() -> None:
        await asyncio.sleep(0.01)
        raise ValueError("Test error")

    # Apply the decorator
    sync_error = to_sync(async_error)

    # Verify the error is propagated correctly
    with pytest.raises(ValueError, match="Test error"):
        sync_error()


def test_to_sync_cannot_be_called_from_async_context() -> None:
    """
    Test that the to_sync decorator raises an error
    when called from an async context.
    """

    # Define an async function
    async def async_function() -> int:
        return 42

    # Apply the decorator
    sync_function = to_sync(async_function)

    # Define an async function that tries to call the sync function
    async def call_sync_from_async() -> int:
        return sync_function()

    # Verify it raises a RuntimeError
    with pytest.raises(RuntimeError):
        asyncio.run(call_sync_from_async())


def test_decorator_preserves_function_metadata() -> None:
    """Test that both decorators preserve function metadata."""

    # Define functions with docstrings and annotations
    def sync_func(x: int) -> str:
        """Sync function docstring."""
        return str(x)

    async def async_func(x: int) -> str:
        """Async function docstring."""
        await asyncio.sleep(0.01)
        return str(x)

    # Apply decorators
    decorated_async = to_async(sync_func)
    decorated_sync = to_sync(async_func)

    # Check metadata is preserved
    assert decorated_async.__name__ == "sync_func"
    assert decorated_async.__doc__ == "Sync function docstring."

    assert decorated_sync.__name__ == "async_func"
    assert decorated_sync.__doc__ == "Async function docstring."
