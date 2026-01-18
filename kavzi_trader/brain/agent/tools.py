from typing import Any

from pydantic_ai import RunContext

from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema


async def get_liquidity_depth(
    ctx: RunContext[TradingDependenciesSchema],
    percent_distance: float,
) -> dict[str, float]:
    """
    Returns placeholder bid/ask liquidity within a percent distance of price.
    """

    _ = (ctx, percent_distance)
    return {"bid_liquidity": 0.0, "ask_liquidity": 0.0}


async def get_recent_liquidations(
    ctx: RunContext[TradingDependenciesSchema],
    hours: int = 4,
) -> list[dict[str, Any]]:
    """
    Returns placeholder liquidation events for the requested window.
    """

    _ = (ctx, hours)
    return []
