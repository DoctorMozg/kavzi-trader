from typing import Any, cast

from kavzi_trader.api.binance.client_base import (
    BinanceClientBase,
    handle_api_errors,
)
from kavzi_trader.api.common.exceptions import ExchangeError


class AccountApi(BinanceClientBase):
    """Futures account, balance and position endpoints (need an API key)."""

    @handle_api_errors
    async def get_account_info(self) -> dict[str, Any]:
        """
        Get futures account information (requires API key).

        Returns:
            Futures account information with totalWalletBalance,
            availableBalance, totalUnrealizedProfit, positions, etc.
        """
        return cast("dict[str, Any]", await self.client.futures_account())

    @handle_api_errors
    async def get_asset_balance(self, asset: str) -> dict[str, Any]:
        """
        Get futures account balance for a specific asset (requires API key).

        Args:
            asset: Asset symbol (e.g., "USDT")

        Returns:
            Asset balance information
        """
        balances = await self.client.futures_account_balance()
        for balance in balances:
            if balance["asset"] == asset:
                return cast("dict[str, Any]", balance)
        raise ExchangeError(f"Asset not found: {asset}")

    @handle_api_errors
    async def futures_get_position_info(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get futures position information.

        Args:
            symbol: Trading pair symbol (optional, returns all if None)

        Returns:
            List of position info dicts with markPrice, liquidationPrice, etc.
        """
        params: dict[str, str] = {}
        if symbol is not None:
            params["symbol"] = symbol

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_position_information(**params),
        )
