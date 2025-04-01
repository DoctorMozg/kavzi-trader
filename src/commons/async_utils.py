"""
Utility functions for working with asynchronous code.
"""

import asyncio
import functools
from typing import Any, Callable, TypeVar, ParamSpec, Awaitable, cast

P = ParamSpec("P")
R = TypeVar("R")


def to_async(func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    """
    Decorator that converts a synchronous function to an asynchronous one.
    
    The decorated function will run in a separate thread using asyncio.to_thread,
    which prevents blocking the event loop when executing I/O-bound operations.
    
    Args:
        func: The synchronous function to convert
        
    Returns:
        An asynchronous function that wraps the original function
        
    Example:
        @to_async
        def read_large_file(path: str) -> str:
            with open(path, 'r') as f:
                return f.read()
                
        # Now you can await the function
        content = await read_large_file("large_file.txt")
    """
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return await asyncio.to_thread(func, *args, **kwargs)
    
    return cast(Callable[P, Awaitable[R]], wrapper)


def to_sync(func: Callable[P, Awaitable[R]]) -> Callable[P, R]:
    """
    Decorator that converts an asynchronous function to a synchronous one.
    
    The decorated function will run the async function in an event loop until completion,
    blocking the current thread until the result is available.
    
    Args:
        func: The asynchronous function to convert
        
    Returns:
        A synchronous function that wraps the original async function
        
    Example:
        @to_sync
        async def fetch_data(url: str) -> dict:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.json()
                    
        # Now you can call it synchronously
        data = fetch_data("https://api.example.com/data")
    """
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "Cannot call sync function from async context - event loop already running"
            )
        except RuntimeError:
            # No event loop running, create a new one
            return asyncio.run(func(*args, **kwargs))
    
    return cast(Callable[P, R], wrapper)