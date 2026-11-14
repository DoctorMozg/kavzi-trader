from datetime import datetime
from typing import Any, cast

from kavzi_trader.api.binance.client_base import (
    BinanceClientBase,
    handle_api_errors,
)


class FuturesDataApi(BinanceClientBase):
    """Futures leverage brackets, funding, open interest and long/short ratio."""

    @handle_api_errors
    async def futures_get_leverage_brackets(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get leverage bracket information for maintenance margin rates.

        Args:
            symbol: Trading pair symbol (optional)

        Returns:
            List of leverage bracket data
        """
        params: dict[str, str] = {}
        if symbol is not None:
            params["symbol"] = symbol

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_leverage_bracket(**params),
        )

    @handle_api_errors
    async def get_funding_rate(
        self,
        symbol: str,
        limit: int = 100,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get funding rate history for a Futures symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            limit: Number of records to return (default 100, max 1000)
            start_time: Start time in milliseconds or datetime
            end_time: End time in milliseconds or datetime

        Returns:
            List of funding rate records
        """
        params: dict[str, Any] = {"symbol": symbol, "limit": limit}

        params |= self._time_params(start_time, end_time)

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_funding_rate(**params),
        )

    @handle_api_errors
    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        """
        Get current open interest for a Futures symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            Open interest data with symbol, openInterest, and time
        """
        return cast(
            "dict[str, Any]",
            await self.client.futures_open_interest(symbol=symbol),
        )

    @handle_api_errors
    async def get_open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get historical open interest for a Futures symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            period: Period interval (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)
            limit: Number of records to return (default 30, max 500)
            start_time: Start time in milliseconds or datetime
            end_time: End time in milliseconds or datetime

        Returns:
            List of historical open interest records
        """
        params: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}

        params |= self._time_params(start_time, end_time)

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_open_interest_hist(**params),
        )

    @handle_api_errors
    async def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get global long/short account ratio for a Futures symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            period: Period interval (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)
            limit: Number of records to return (default 30, max 500)
            start_time: Start time in milliseconds or datetime
            end_time: End time in milliseconds or datetime

        Returns:
            List of long/short ratio records
        """
        params: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}

        params |= self._time_params(start_time, end_time)

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_global_longshort_ratio(**params),
        )
