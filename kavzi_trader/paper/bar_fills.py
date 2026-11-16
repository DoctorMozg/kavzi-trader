"""How one OHLC bar fills simulated orders; pure price rules, no state."""

from decimal import Decimal

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.order_enums import OrderSide, OrderType
from kavzi_trader.domain.order_response import OrderResponseSchema


def triggered_fill_price(
    order: OrderResponseSchema,
    bar: CandlestickSchema,
) -> Decimal | None:
    """Fill price of a stop- or take-profit-market the bar reached, else None."""
    trigger = order.stop_price
    if trigger is None:
        raise ValueError(f"Order {order.order_id} has no trigger price")
    is_stop = order.type == OrderType.STOP_MARKET
    # A SELL stop / BUY take-profit triggers on a falling price, and vice versa.
    if (order.side == OrderSide.SELL) == is_stop:
        if bar.low_price > trigger:
            return None
        # A stop gapped through fills at the open; a take-profit never beats its
        # trigger, so a favourable gap cannot inflate PnL.
        return min(trigger, bar.open_price) if is_stop else trigger
    if bar.high_price < trigger:
        return None
    return max(trigger, bar.open_price) if is_stop else trigger


def limit_touched(order: OrderResponseSchema, bar: CandlestickSchema) -> bool:
    if order.side == OrderSide.BUY:
        return bar.low_price <= order.price
    return bar.high_price >= order.price


def liquidation_price(
    side: str,
    entry_price: Decimal,
    leverage: int,
    maintenance_margin_rate: Decimal,
) -> Decimal:
    """Isolated-margin liquidation price from Binance's formula with cum = 0."""
    inverse = Decimal(1) / Decimal(leverage)
    if side == "LONG":
        return entry_price * (1 - inverse) / (1 - maintenance_margin_rate)
    return entry_price * (1 + inverse) / (1 + maintenance_margin_rate)


def is_beyond(side: str, price: Decimal, threshold: Decimal) -> bool:
    """True when price has moved against a position at least to threshold."""
    return price <= threshold if side == "LONG" else price >= threshold


def adverse_extreme(side: str, bar: CandlestickSchema) -> Decimal:
    return bar.low_price if side == "LONG" else bar.high_price
