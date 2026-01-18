from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.models import OrderBookEntrySchema, OrderBookSchema
from kavzi_trader.brain.agent.tools import get_liquidity_depth, get_recent_liquidations


@pytest.mark.asyncio()
async def test_get_liquidity_depth_returns_structure() -> None:
    orderbook = OrderBookSchema(
        bids=[OrderBookEntrySchema(price=Decimal("100"), qty=Decimal("1"))],
        asks=[OrderBookEntrySchema(price=Decimal("101"), qty=Decimal("1"))],
    )
    deps = SimpleNamespace(
        symbol="BTCUSDT",
        current_price=Decimal("100"),
        exchange_client=SimpleNamespace(
            get_orderbook=AsyncMock(return_value=orderbook),
        ),
    )
    ctx = SimpleNamespace(deps=deps)
    result = await get_liquidity_depth(ctx, percent_distance=0.5)
    assert "bid_liquidity" in result, "Expected bid liquidity key."
    assert "ask_liquidity" in result, "Expected ask liquidity key."


@pytest.mark.asyncio()
async def test_get_recent_liquidations_returns_list() -> None:
    deps = SimpleNamespace(
        symbol="BTCUSDT",
        event_store=SimpleNamespace(
            query=AsyncMock(return_value=[]),
        ),
    )
    ctx = SimpleNamespace(deps=deps)
    result = await get_recent_liquidations(ctx, hours=4)
    assert isinstance(result, list), "Expected list result."
