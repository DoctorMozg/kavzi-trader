from decimal import Decimal

from kavzi_trader.domain.symbol_filters import SymbolFiltersSchema
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision

BTC_FILTERS = SymbolFiltersSchema(
    symbol="BTCUSDT",
    step_size=Decimal("0.01"),
    min_qty=Decimal("0.01"),
    max_qty=Decimal(1000),
    market_step_size=Decimal("0.01"),
    market_min_qty=Decimal("0.01"),
    market_max_qty=Decimal(500),
    tick_size=Decimal("0.5"),
    min_notional=Decimal(100),
)


def make_precision() -> SymbolPrecision:
    """In-memory filters standing in for exchangeInfo; no network."""
    return SymbolPrecision([BTC_FILTERS])
