from decimal import Decimal

import pytest

from kavzi_trader.brain.schemas.analyst import KeyLevelSchema
from kavzi_trader.spine.execution.geometry import TradeGeometryCalculator
from kavzi_trader.spine.execution.geometry_schemas import (
    EntryTactic,
    GeometryInputsSchema,
    GeometryRejectionSchema,
    TargetStyle,
    TradeDirection,
    TradeGeometrySchema,
    TradeStructureSchema,
)
from kavzi_trader.spine.risk.config import RiskConfigSchema


@pytest.fixture
def calc() -> TradeGeometryCalculator:
    return TradeGeometryCalculator(RiskConfigSchema())


def _level(price: str, level_type: str) -> KeyLevelSchema:
    return KeyLevelSchema.model_validate(
        {"price": Decimal(price), "level_type": level_type, "reason": "test level"}
    )


def _inputs(
    price: str = "100",
    atr: str | None = "1",
    levels: list[KeyLevelSchema] | None = None,
    leverage: int = 1,
) -> GeometryInputsSchema:
    return GeometryInputsSchema(
        symbol="BTCUSDT",
        current_price=Decimal(price),
        atr_14=Decimal(atr) if atr is not None else None,
        key_levels=levels or [],
        leverage=leverage,
    )


def _structure(
    direction: TradeDirection = "LONG",
    entry_tactic: EntryTactic = "IMMEDIATE",
    entry_level_index: int | None = None,
    stop_level_index: int | None = None,
    stop_atr_multiplier: str | None = "1.0",
    target_style: TargetStyle = "ATR_2X",
) -> TradeStructureSchema:
    return TradeStructureSchema(
        direction=direction,
        entry_tactic=entry_tactic,
        entry_level_index=entry_level_index,
        stop_level_index=stop_level_index,
        stop_atr_multiplier=(
            Decimal(stop_atr_multiplier) if stop_atr_multiplier is not None else None
        ),
        target_style=target_style,
    )


def _expect_geometry(result: object) -> TradeGeometrySchema:
    assert isinstance(result, TradeGeometrySchema), f"expected geometry, got {result}"
    return result


def _expect_rejection(result: object, code: str) -> GeometryRejectionSchema:
    assert isinstance(result, GeometryRejectionSchema), (
        f"expected rejection, got {result}"
    )
    assert result.code == code, result.detail
    return result


class TestImmediateAtrGeometry:
    def test_long_one_atr_stop_two_atr_target(
        self, calc: TradeGeometryCalculator
    ) -> None:
        geometry = _expect_geometry(calc.compute(_structure(), _inputs()))
        assert geometry.entry == Decimal(100)
        assert geometry.stop_loss == Decimal(99)
        assert geometry.take_profit == Decimal(102)
        assert geometry.rr_ratio == Decimal(2)
        assert geometry.adjustments == []

    def test_short_mirrors_long(self, calc: TradeGeometryCalculator) -> None:
        geometry = _expect_geometry(
            calc.compute(_structure(direction="SHORT"), _inputs())
        )
        assert geometry.entry == Decimal(100)
        assert geometry.stop_loss == Decimal(101)
        assert geometry.take_profit == Decimal(98)
        assert geometry.rr_ratio == Decimal(2)

    def test_wide_stop_extends_target_to_exact_min_rr(
        self, calc: TradeGeometryCalculator
    ) -> None:
        geometry = _expect_geometry(
            calc.compute(_structure(stop_atr_multiplier="1.5"), _inputs())
        )
        assert geometry.stop_loss == Decimal("98.5")
        assert geometry.take_profit == Decimal("103.0")
        assert geometry.rr_ratio == Decimal(2)
        assert any("extended" in note for note in geometry.adjustments)

    def test_stop_too_wide_for_realistic_target_rejected(
        self, calc: TradeGeometryCalculator
    ) -> None:
        result = calc.compute(_structure(stop_atr_multiplier="2.0"), _inputs())
        _expect_rejection(result, "TP_UNREACHABLE")

    def test_three_atr_target_keeps_native_rr(
        self, calc: TradeGeometryCalculator
    ) -> None:
        geometry = _expect_geometry(
            calc.compute(_structure(target_style="ATR_3X"), _inputs())
        )
        assert geometry.take_profit == Decimal(103)
        assert geometry.rr_ratio == Decimal(3)

    def test_multiplier_below_min_rejected(self, calc: TradeGeometryCalculator) -> None:
        result = calc.compute(_structure(stop_atr_multiplier="0.3"), _inputs())
        _expect_rejection(result, "INVALID_STRUCTURE")

    def test_missing_stop_anchor_rejected(self, calc: TradeGeometryCalculator) -> None:
        result = calc.compute(_structure(stop_atr_multiplier=None), _inputs())
        _expect_rejection(result, "INVALID_STRUCTURE")

    def test_missing_atr_rejected(self, calc: TradeGeometryCalculator) -> None:
        result = calc.compute(_structure(), _inputs(atr=None))
        _expect_rejection(result, "NO_ATR")


class TestStructuralTargets:
    def test_nearest_qualifying_resistance_wins(
        self, calc: TradeGeometryCalculator
    ) -> None:
        levels = [_level("101", "RESISTANCE"), _level("104", "RESISTANCE")]
        geometry = _expect_geometry(
            calc.compute(
                _structure(target_style="STRUCTURAL"),
                _inputs(levels=levels),
            )
        )
        assert geometry.take_profit == Decimal(104)
        assert geometry.rr_ratio == Decimal(4)

    def test_no_qualifying_level_falls_back_to_extension(
        self, calc: TradeGeometryCalculator
    ) -> None:
        levels = [_level("101", "RESISTANCE")]
        geometry = _expect_geometry(
            calc.compute(
                _structure(target_style="STRUCTURAL"),
                _inputs(levels=levels),
            )
        )
        assert geometry.take_profit == Decimal(102)
        assert geometry.rr_ratio == Decimal(2)
        assert any("extended" in note for note in geometry.adjustments)

    def test_short_structural_support_target(
        self, calc: TradeGeometryCalculator
    ) -> None:
        levels = [_level("96", "SUPPORT")]
        geometry = _expect_geometry(
            calc.compute(
                _structure(direction="SHORT", target_style="STRUCTURAL"),
                _inputs(levels=levels),
            )
        )
        assert geometry.take_profit == Decimal(96)

    def test_wrong_side_levels_ignored_for_targets(
        self, calc: TradeGeometryCalculator
    ) -> None:
        levels = [_level("95", "SUPPORT")]
        geometry = _expect_geometry(
            calc.compute(
                _structure(target_style="STRUCTURAL"),
                _inputs(levels=levels),
            )
        )
        # Support below entry is not a LONG target; extension applies.
        assert geometry.take_profit == Decimal(102)


class TestLevelAnchoredStops:
    def test_stop_placed_buffer_beyond_support(
        self, calc: TradeGeometryCalculator
    ) -> None:
        levels = [_level("99", "SUPPORT")]
        geometry = _expect_geometry(
            calc.compute(
                _structure(stop_level_index=0, stop_atr_multiplier=None),
                _inputs(levels=levels),
            )
        )
        assert geometry.stop_loss == Decimal("98.9")
        assert geometry.rr_ratio == Decimal(2)
        assert geometry.take_profit == Decimal("102.2")

    def test_anchor_too_far_rejected(self, calc: TradeGeometryCalculator) -> None:
        levels = [_level("96", "SUPPORT")]
        result = calc.compute(
            _structure(stop_level_index=0, stop_atr_multiplier=None),
            _inputs(levels=levels),
        )
        _expect_rejection(result, "SL_TOO_WIDE")

    def test_anchor_too_close_widened_to_minimum(
        self, calc: TradeGeometryCalculator
    ) -> None:
        levels = [_level("99.8", "SUPPORT")]
        geometry = _expect_geometry(
            calc.compute(
                _structure(stop_level_index=0, stop_atr_multiplier=None),
                _inputs(levels=levels),
            )
        )
        assert geometry.stop_loss == Decimal("99.5")
        assert any("widened" in note for note in geometry.adjustments)

    def test_anchor_wrong_type_rejected(self, calc: TradeGeometryCalculator) -> None:
        levels = [_level("99", "RESISTANCE")]
        result = calc.compute(
            _structure(stop_level_index=0, stop_atr_multiplier=None),
            _inputs(levels=levels),
        )
        _expect_rejection(result, "INVALID_STRUCTURE")

    def test_anchor_index_out_of_range_rejected(
        self, calc: TradeGeometryCalculator
    ) -> None:
        result = calc.compute(
            _structure(stop_level_index=2, stop_atr_multiplier=None),
            _inputs(levels=[_level("99", "SUPPORT")]),
        )
        _expect_rejection(result, "INVALID_STRUCTURE")


class TestPullbackEntries:
    def test_long_pullback_to_support(self, calc: TradeGeometryCalculator) -> None:
        levels = [_level("99", "SUPPORT")]
        geometry = _expect_geometry(
            calc.compute(
                _structure(entry_tactic="PULLBACK_TO_LEVEL", entry_level_index=0),
                _inputs(levels=levels),
            )
        )
        assert geometry.entry == Decimal(99)
        assert geometry.stop_loss == Decimal(98)
        assert geometry.take_profit == Decimal(101)

    def test_short_pullback_to_resistance(self, calc: TradeGeometryCalculator) -> None:
        levels = [_level("101", "RESISTANCE")]
        geometry = _expect_geometry(
            calc.compute(
                _structure(
                    direction="SHORT",
                    entry_tactic="PULLBACK_TO_LEVEL",
                    entry_level_index=0,
                ),
                _inputs(levels=levels),
            )
        )
        assert geometry.entry == Decimal(101)
        assert geometry.stop_loss == Decimal(102)
        assert geometry.take_profit == Decimal(99)

    def test_pullback_without_index_rejected(
        self, calc: TradeGeometryCalculator
    ) -> None:
        result = calc.compute(
            _structure(entry_tactic="PULLBACK_TO_LEVEL"),
            _inputs(levels=[_level("99", "SUPPORT")]),
        )
        _expect_rejection(result, "INVALID_STRUCTURE")

    def test_pullback_to_wrong_side_level_rejected(
        self, calc: TradeGeometryCalculator
    ) -> None:
        levels = [_level("101", "RESISTANCE")]
        result = calc.compute(
            _structure(entry_tactic="PULLBACK_TO_LEVEL", entry_level_index=0),
            _inputs(levels=levels),
        )
        _expect_rejection(result, "INVALID_STRUCTURE")

    def test_pullback_support_above_price_rejected(
        self, calc: TradeGeometryCalculator
    ) -> None:
        levels = [_level("101", "SUPPORT")]
        result = calc.compute(
            _structure(entry_tactic="PULLBACK_TO_LEVEL", entry_level_index=0),
            _inputs(levels=levels),
        )
        _expect_rejection(result, "INVALID_STRUCTURE")


class TestLiquidationBudget:
    def test_stop_beyond_liquidation_budget_rejected(
        self, calc: TradeGeometryCalculator
    ) -> None:
        # 50x: liquidation ~2.0 away, budget 1.6 with 20% buffer.
        result = calc.compute(
            _structure(stop_atr_multiplier="2.0", target_style="ATR_3X"),
            _inputs(leverage=50),
        )
        _expect_rejection(result, "SL_BEYOND_LIQUIDATION")

    def test_stop_within_budget_accepted(self, calc: TradeGeometryCalculator) -> None:
        geometry = _expect_geometry(
            calc.compute(
                _structure(stop_atr_multiplier="1.5"),
                _inputs(leverage=50),
            )
        )
        assert geometry.rr_ratio == Decimal(2)

    def test_default_leverage_skips_liquidation_check(
        self, calc: TradeGeometryCalculator
    ) -> None:
        geometry = _expect_geometry(calc.compute(_structure(), _inputs(leverage=5)))
        assert geometry.stop_loss == Decimal(99)


class TestPercentFloor:
    def test_compressed_atr_cannot_produce_legal_stop(
        self, calc: TradeGeometryCalculator
    ) -> None:
        # ATR 0.04% of price: percent floor 0.15 exceeds 3x ATR max 0.12.
        result = calc.compute(_structure(), _inputs(atr="0.04"))
        _expect_rejection(result, "SL_TOO_WIDE")

    def test_floor_widening_at_exact_target_ceiling(
        self, calc: TradeGeometryCalculator
    ) -> None:
        # ATR 0.1%: stop widened to 0.15 (1.5x ATR); required target 0.30
        # sits exactly on the 3x ATR ceiling.
        geometry = _expect_geometry(calc.compute(_structure(), _inputs(atr="0.1")))
        assert geometry.stop_loss == Decimal("99.85")
        assert geometry.take_profit == Decimal("100.30")
        assert geometry.rr_ratio == Decimal(2)


class TestEstimate:
    def test_normal_conditions_viable(self, calc: TradeGeometryCalculator) -> None:
        viability = calc.estimate("LONG", _inputs())
        assert viability.viable
        assert viability.best_rr == Decimal(6)

    def test_compressed_atr_not_viable(self, calc: TradeGeometryCalculator) -> None:
        viability = calc.estimate("LONG", _inputs(atr="0.04"))
        assert not viability.viable
        assert viability.reason is not None
        assert "compressed" in viability.reason

    def test_far_structural_level_raises_best_rr(
        self, calc: TradeGeometryCalculator
    ) -> None:
        viability = calc.estimate("LONG", _inputs(levels=[_level("110", "RESISTANCE")]))
        assert viability.viable
        assert viability.best_rr == Decimal(20)

    def test_short_uses_supports_below(self, calc: TradeGeometryCalculator) -> None:
        viability = calc.estimate("SHORT", _inputs(levels=[_level("90", "SUPPORT")]))
        assert viability.viable
        assert viability.best_rr == Decimal(20)

    def test_leverage_budget_blocks_min_stop(
        self, calc: TradeGeometryCalculator
    ) -> None:
        # ATR 2%: min stop 1.0; 125x liquidation budget 0.64.
        viability = calc.estimate("LONG", _inputs(atr="2", leverage=125))
        assert not viability.viable
        assert viability.reason is not None
        assert "liquidation" in viability.reason

    def test_no_atr_not_viable(self, calc: TradeGeometryCalculator) -> None:
        viability = calc.estimate("LONG", _inputs(atr=None))
        assert not viability.viable
