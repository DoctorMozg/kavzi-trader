from decimal import Decimal

import pytest

from kavzi_trader.spine.precision.symbol_precision import (
    OrderPrecisionError,
    SymbolPrecision,
)

SYMBOL = "BTCUSDT"


class TestQuantity:
    def test_floors_to_step(self, precision: SymbolPrecision) -> None:
        assert precision.round_qty(SYMBOL, Decimal("1.239")) == Decimal("1.23")

    def test_aligned_quantity_is_unchanged(self, precision: SymbolPrecision) -> None:
        assert precision.round_qty(SYMBOL, Decimal("1.23")) == Decimal("1.23")

    def test_ceil_never_goes_below_input(self, precision: SymbolPrecision) -> None:
        assert precision.ceil_qty(SYMBOL, Decimal("1.231")) == Decimal("1.24")

    def test_rejects_below_min_qty(self, precision: SymbolPrecision) -> None:
        qty = precision.round_qty(SYMBOL, Decimal("0.009"))
        assert qty == 0
        assert precision.check_qty(SYMBOL, qty) is not None
        assert "minQty" in (precision.check_qty(SYMBOL, Decimal("0.005")) or "")

    def test_rejects_below_min_notional(self, precision: SymbolPrecision) -> None:
        reason = precision.check_qty(SYMBOL, Decimal("0.5"), Decimal(100))
        assert reason is not None
        assert "notional" in reason

    def test_reduce_only_skips_notional(self, precision: SymbolPrecision) -> None:
        assert (
            precision.check_qty(SYMBOL, Decimal("0.5"), Decimal(100), reduce_only=True)
            is None
        )

    def test_rejects_above_max_qty(self, precision: SymbolPrecision) -> None:
        assert "maxQty" in (
            precision.check_qty(SYMBOL, Decimal(501), market=True) or ""
        )

    def test_unknown_symbol_fails_loudly(self, precision: SymbolPrecision) -> None:
        with pytest.raises(OrderPrecisionError, match="ETHUSDT"):
            precision.round_qty("ETHUSDT", Decimal(1))


class TestPrice:
    def test_directional_rounding(self, precision: SymbolPrecision) -> None:
        assert precision.round_price(SYMBOL, Decimal("100.3"), "DOWN") == Decimal(100)
        assert precision.round_price(SYMBOL, Decimal("100.3"), "UP") == Decimal("100.5")

    @pytest.mark.parametrize(
        ("is_long", "expected"),
        [(True, Decimal("100.5")), (False, Decimal(100))],
    )
    def test_stop_loss_rounds_toward_entry(
        self,
        precision: SymbolPrecision,
        is_long: bool,
        expected: Decimal,
    ) -> None:
        # Long SL sits below entry, so toward entry is up; short is the mirror.
        assert (
            precision.round_stop_loss(SYMBOL, Decimal("100.3"), is_long=is_long)
            == expected
        )

    @pytest.mark.parametrize(
        ("is_long", "expected"),
        [(True, Decimal(100)), (False, Decimal("100.5"))],
    )
    def test_take_profit_rounds_toward_entry(
        self,
        precision: SymbolPrecision,
        is_long: bool,
        expected: Decimal,
    ) -> None:
        assert (
            precision.round_take_profit(SYMBOL, Decimal("100.3"), is_long=is_long)
            == expected
        )
