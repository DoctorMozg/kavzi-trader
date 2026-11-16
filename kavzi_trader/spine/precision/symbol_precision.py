import logging
from collections.abc import Iterable
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Literal

from kavzi_trader.domain.symbol_filters import SymbolFiltersSchema

logger = logging.getLogger(__name__)

RoundDirection = Literal["UP", "DOWN"]


class OrderPrecisionError(ValueError):
    """Raised when an order cannot be expressed on the exchange's grid."""


class SymbolPrecision:
    """Snaps quantities and prices to the exchange's per-symbol filters."""

    def __init__(self, filters: Iterable[SymbolFiltersSchema]) -> None:
        self._filters = {f.symbol: f for f in filters}

    def round_qty(
        self,
        symbol: str,
        qty: Decimal,
        *,
        market: bool = False,
    ) -> Decimal:
        """Floor to the lot step so the order never exceeds the planned size."""
        step = self._step(symbol, market)
        return (qty / step).to_integral_value(rounding=ROUND_FLOOR) * step

    def ceil_qty(self, symbol: str, qty: Decimal, *, market: bool = False) -> Decimal:
        step = self._step(symbol, market)
        return (qty / step).to_integral_value(rounding=ROUND_CEILING) * step

    def round_price(
        self,
        symbol: str,
        price: Decimal,
        direction: RoundDirection,
    ) -> Decimal:
        tick = self._filters_for(symbol).tick_size
        rounding = ROUND_CEILING if direction == "UP" else ROUND_FLOOR
        return (price / tick).to_integral_value(rounding=rounding) * tick

    def round_stop_loss(
        self,
        symbol: str,
        price: Decimal,
        *,
        is_long: bool,
    ) -> Decimal:
        """Round toward entry so the loss never exceeds the planned risk."""
        return self.round_price(symbol, price, "UP" if is_long else "DOWN")

    def round_take_profit(
        self,
        symbol: str,
        price: Decimal,
        *,
        is_long: bool,
    ) -> Decimal:
        """Round toward entry so the target stays reachable."""
        return self.round_price(symbol, price, "DOWN" if is_long else "UP")

    def check_qty(
        self,
        symbol: str,
        qty: Decimal,
        price: Decimal | None = None,
        *,
        market: bool = False,
        reduce_only: bool = False,
    ) -> str | None:
        """Reason an already-rounded quantity is not tradable, else None."""
        filters = self._filters_for(symbol)
        min_qty = filters.market_min_qty if market else filters.min_qty
        max_qty = filters.market_max_qty if market else filters.max_qty
        if qty <= 0:
            return "quantity rounds to zero at the exchange step size"
        if qty < min_qty:
            return f"quantity {qty} below exchange minQty {min_qty}"
        if qty > max_qty:
            return f"quantity {qty} above exchange maxQty {max_qty}"
        # Reduce-only orders are exempt from the notional minimum.
        if not reduce_only and price is not None:
            notional = qty * price
            if notional < filters.min_notional:
                return (
                    f"notional {notional} below exchange minimum {filters.min_notional}"
                )
        return None

    def _step(self, symbol: str, market: bool) -> Decimal:
        filters = self._filters_for(symbol)
        return filters.market_step_size if market else filters.step_size

    def _filters_for(self, symbol: str) -> SymbolFiltersSchema:
        filters = self._filters.get(symbol)
        if filters is None:
            raise OrderPrecisionError(f"No exchange filters loaded for {symbol}")
        return filters
