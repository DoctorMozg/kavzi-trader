"""
Exceptions for API connectors.

This module defines the exception classes used by the API connectors.
"""


class APIError(Exception):
    """Base class for all API errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class AuthenticationError(APIError):
    """Raised when authentication fails."""

    def __str__(self) -> str:
        return f"Authentication Error: {self.message}"


class RateLimitError(APIError):
    """Raised when rate limit is exceeded."""

    def __str__(self) -> str:
        return f"Rate Limit Error: {self.message}"


class RequestError(APIError):
    """Raised when an HTTP request fails."""

    def __str__(self) -> str:
        return f"Request Error: {self.message}"


class ExchangeError(APIError):
    """Raised for exchange-specific errors."""

    def __init__(self, message: str, code: int | None = None) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:
        if self.code:
            return f"Exchange Error ({self.code}): {self.message}"
        return f"Exchange Error: {self.message}"
