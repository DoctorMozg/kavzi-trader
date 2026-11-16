from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.api.binance.symbol_filters_loader import (
    FuturesSymbolFiltersLoader,
    SymbolFiltersLoadError,
)


def _symbol(name: str, *, skip: str | None = None) -> dict[str, Any]:
    filters = [
        {
            "filterType": "PRICE_FILTER",
            "tickSize": "0.10",
            "minPrice": "1",
            "maxPrice": "1000000",
        },
        {
            "filterType": "LOT_SIZE",
            "stepSize": "0.001",
            "minQty": "0.001",
            "maxQty": "1000",
        },
        {
            "filterType": "MARKET_LOT_SIZE",
            "stepSize": "0.001",
            "minQty": "0.001",
            "maxQty": "120",
        },
        {"filterType": "MIN_NOTIONAL", "notional": "100"},
    ]
    return {
        "symbol": name,
        "filters": [f for f in filters if f["filterType"] != skip],
    }


def _loader(*symbols: dict[str, Any]) -> FuturesSymbolFiltersLoader:
    client = MagicMock()
    client.futures_get_exchange_info = AsyncMock(
        return_value={"symbols": list(symbols)}
    )
    return FuturesSymbolFiltersLoader(client)


async def test_parses_futures_filters() -> None:
    [btc] = await _loader(_symbol("BTCUSDT"), _symbol("ETHUSDT")).load(["BTCUSDT"])
    assert btc.step_size == Decimal("0.001")
    assert btc.market_max_qty == Decimal(120)
    assert btc.tick_size == Decimal("0.10")
    assert btc.min_notional == Decimal(100)


async def test_unlisted_symbol_fails_startup() -> None:
    with pytest.raises(SymbolFiltersLoadError, match="XRPUSDT"):
        await _loader(_symbol("BTCUSDT")).load(["XRPUSDT"])


async def test_missing_required_filter_fails_startup() -> None:
    with pytest.raises(SymbolFiltersLoadError, match="MIN_NOTIONAL"):
        await _loader(_symbol("BTCUSDT", skip="MIN_NOTIONAL")).load(["BTCUSDT"])
