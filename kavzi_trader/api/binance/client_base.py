import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Concatenate

from binance.async_client import AsyncClient as BinanceAPIClient
from binance.exceptions import BinanceAPIException, BinanceRequestException

from kavzi_trader.api.binance.constants import (
    ERROR_CODE_INVALID_API_KEY,
    ERROR_CODE_RATE_LIMIT_EXCEEDED,
    ERROR_CODE_UNAUTHORIZED,
)
from kavzi_trader.api.common.exceptions import (
    APIError,
    AuthenticationError,
    ExchangeError,
    RateLimitError,
    RequestError,
)
from kavzi_trader.commons.time_utility import MILLISECONDS_IN_SECOND

logger = logging.getLogger(__name__)


def handle_api_errors[TClient: BinanceClientBase, **P, R](
    func: Callable[Concatenate[TClient, P], Awaitable[R]],
) -> Callable[Concatenate[TClient, P], Awaitable[R]]:
    """Map Binance library exceptions raised by an async method to our own."""

    @wraps(func)
    async def wrapper(self: TClient, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(self, *args, **kwargs)
        except (BinanceAPIException, BinanceRequestException) as error:
            try:
                self._handle_error(error)
            except APIError as mapped:
                raise mapped from error
            raise

    return wrapper


class BinanceClientBase:
    """Shared state and helpers for the endpoint groups composing BinanceClient."""

    client: BinanceAPIClient

    @staticmethod
    def _to_ms(value: int | datetime) -> int:
        """Convert a datetime (naive means UTC) or a ms timestamp to ms."""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return int(value.timestamp() * MILLISECONDS_IN_SECOND)
        return value

    @classmethod
    def _time_params(
        cls,
        start_time: int | datetime | None,
        end_time: int | datetime | None = None,
    ) -> dict[str, int]:
        """Build the optional startTime/endTime query parameters."""
        params: dict[str, int] = {}
        if start_time is not None:
            params["startTime"] = cls._to_ms(start_time)
        if end_time is not None:
            params["endTime"] = cls._to_ms(end_time)
        return params

    def _handle_error(self, error: Exception) -> None:
        """
        Handle API errors and map them to our exception types.

        Args:
            error: The exception to handle

        Raises:
            AuthenticationError: For authentication issues
            RateLimitError: For rate limit issues
            RequestError: For network or request issues
            ExchangeError: For Binance-specific errors
            APIError: For generic API errors
        """
        message = str(error)
        logger.debug("Handling API error: %s", message)

        if isinstance(error, BinanceAPIException):
            error_code = error.code

            # Authentication errors
            if error_code in (ERROR_CODE_INVALID_API_KEY, ERROR_CODE_UNAUTHORIZED):
                raise AuthenticationError(message)

            # Rate limit errors
            if error_code == ERROR_CODE_RATE_LIMIT_EXCEEDED:
                raise RateLimitError(message)

            # Exchange-specific errors
            raise ExchangeError(message, code=error_code)

        if isinstance(error, BinanceRequestException):
            raise RequestError(message)

        raise APIError(f"Unexpected error: {message}")
