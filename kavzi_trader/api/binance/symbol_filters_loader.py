import logging
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.domain.symbol_filters import SymbolFiltersSchema

logger = logging.getLogger(__name__)


class SymbolFiltersLoadError(RuntimeError):
    """Raised when exchangeInfo lacks a requested symbol or a required filter."""


class FuturesSymbolFiltersLoader:
    """Reads LOT_SIZE, MARKET_LOT_SIZE, PRICE_FILTER and MIN_NOTIONAL per symbol."""

    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    async def load(self, symbols: Iterable[str]) -> list[SymbolFiltersSchema]:
        info = await self._client.futures_get_exchange_info()
        by_symbol = {s["symbol"]: s for s in info["symbols"]}
        loaded: list[SymbolFiltersSchema] = []
        for symbol in symbols:
            raw = by_symbol.get(symbol)
            if raw is None:
                raise SymbolFiltersLoadError(
                    f"{symbol} not listed in futures exchangeInfo",
                )
            loaded.append(self._parse(symbol, raw))
        logger.info("Loaded exchange filters for %d symbols", len(loaded))
        return loaded

    # Any: raw exchangeInfo symbol entry with a heterogeneous filter list.
    @staticmethod
    def _parse(symbol: str, raw: dict[str, Any]) -> SymbolFiltersSchema:
        filters = {f["filterType"]: f for f in raw["filters"]}
        missing = {"LOT_SIZE", "PRICE_FILTER", "MIN_NOTIONAL"} - filters.keys()
        if missing:
            raise SymbolFiltersLoadError(
                f"{symbol} exchangeInfo is missing filters {sorted(missing)}",
            )
        lot = filters["LOT_SIZE"]
        market = filters.get("MARKET_LOT_SIZE", lot)
        return SymbolFiltersSchema(
            symbol=symbol,
            step_size=Decimal(lot["stepSize"]),
            min_qty=Decimal(lot["minQty"]),
            max_qty=Decimal(lot["maxQty"]),
            market_step_size=Decimal(market["stepSize"]),
            market_min_qty=Decimal(market["minQty"]),
            market_max_qty=Decimal(market["maxQty"]),
            tick_size=Decimal(filters["PRICE_FILTER"]["tickSize"]),
            min_notional=Decimal(filters["MIN_NOTIONAL"]["notional"]),
        )
