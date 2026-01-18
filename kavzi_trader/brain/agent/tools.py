from datetime import timedelta
from decimal import Decimal
from typing import Any

from pydantic_ai import RunContext

from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema
from kavzi_trader.commons.time_utility import utc_now


async def get_liquidity_depth(
    ctx: RunContext[TradingDependenciesSchema],
    percent_distance: float,
) -> dict[str, float]:
    """
    Returns placeholder bid/ask liquidity within a percent distance of price.
    """

    orderbook = await ctx.deps.exchange_client.get_orderbook(
        symbol=ctx.deps.symbol,
        limit=100,
    )
    current_price = ctx.deps.current_price
    percent = Decimal(str(percent_distance))
    lower_bound = current_price * (Decimal("1") - percent / Decimal("100"))
    upper_bound = current_price * (Decimal("1") + percent / Decimal("100"))

    bid_liquidity = sum(
        bid.price * bid.qty for bid in orderbook.bids if bid.price >= lower_bound
    )
    ask_liquidity = sum(
        ask.price * ask.qty for ask in orderbook.asks if ask.price <= upper_bound
    )
    return {
        "bid_liquidity": float(bid_liquidity),
        "ask_liquidity": float(ask_liquidity),
    }


async def get_recent_liquidations(
    ctx: RunContext[TradingDependenciesSchema],
    hours: int = 4,
) -> list[dict[str, Any]]:
    """
    Returns placeholder liquidation events for the requested window.
    """

    cutoff = utc_now() - timedelta(hours=hours)
    events = await ctx.deps.event_store.query(
        stream="kt:events:liquidations",
        after=cutoff,
        symbol=ctx.deps.symbol,
    )
    return [
        {
            "timestamp": event.timestamp.isoformat(),
            "side": event.data.get("side"),
            "quantity": event.data.get("quantity"),
            "price": event.data.get("price"),
        }
        for event in events
    ]
