import pytest

from kavzi_trader.brain.agent.tools import get_liquidity_depth, get_recent_liquidations


@pytest.mark.asyncio()
async def test_get_liquidity_depth_returns_structure() -> None:
    result = await get_liquidity_depth(None, percent_distance=0.5)
    assert "bid_liquidity" in result, "Expected bid liquidity key."
    assert "ask_liquidity" in result, "Expected ask liquidity key."


@pytest.mark.asyncio()
async def test_get_recent_liquidations_returns_list() -> None:
    result = await get_recent_liquidations(None, hours=4)
    assert isinstance(result, list), "Expected list result."
