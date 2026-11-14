import pytest

from kavzi_trader.brain.confluence_thresholds import (
    CONFLUENCE_ENTER_MIN,
    CONFLUENCE_REJECT_MAX,
    confluence_enter_min_for_regime,
    effective_min_algo_confluence,
    effective_regime_gate,
)
from kavzi_trader.domain.algorithm_confluence import ALGO_SIGNAL_COUNT
from kavzi_trader.domain.volatility_regime import VolatilityRegime


@pytest.mark.parametrize(
    ("regime", "expected_gate"),
    [
        (VolatilityRegime.NORMAL, 6),
        (VolatilityRegime.HIGH, 7),
        (VolatilityRegime.EXTREME, 8),
        (VolatilityRegime.LOW, 7),
    ],
)
def test_regime_enter_min_table(
    regime: VolatilityRegime,
    expected_gate: int,
) -> None:
    assert confluence_enter_min_for_regime(regime) == expected_gate


def test_constant_matches_normal_gate() -> None:
    # Legacy CONFLUENCE_ENTER_MIN must remain the NORMAL-regime alias so
    # callers that still import the constant keep behavioural parity.
    assert (
        confluence_enter_min_for_regime(
            VolatilityRegime.NORMAL,
        )
        == CONFLUENCE_ENTER_MIN
    )


def test_reject_band_below_every_gate() -> None:
    # CONFLUENCE_REJECT_MAX must stay strictly below the tightest regime
    # gate so the borderline WAIT band exists under every regime.
    for regime in VolatilityRegime:
        assert confluence_enter_min_for_regime(regime) > CONFLUENCE_REJECT_MAX


@pytest.mark.parametrize(
    ("available", "expected"),
    [
        (ALGO_SIGNAL_COUNT, {"NORMAL": 6, "HIGH": 7, "LOW": 7, "EXTREME": 8}),
        (6, {"NORMAL": 5, "HIGH": 6, "LOW": 6, "EXTREME": 7}),
        (5, {"NORMAL": 5, "HIGH": 6, "LOW": 6, "EXTREME": 6}),
    ],
)
def test_effective_gate_scales_with_available_signals(
    available: int,
    expected: dict[str, int],
) -> None:
    gates = {
        regime.name: effective_regime_gate(regime, available)
        for regime in VolatilityRegime
    }

    assert gates == expected


def test_effective_gate_rejects_out_of_range_availability() -> None:
    with pytest.raises(ValueError, match="available_signals"):
        effective_regime_gate(VolatilityRegime.NORMAL, ALGO_SIGNAL_COUNT + 1)


@pytest.mark.parametrize(
    ("available", "expected"),
    [(ALGO_SIGNAL_COUNT, 3), (5, 2), (0, 0)],
)
def test_effective_min_algo_follows_normal_gate_reduction(
    available: int,
    expected: int,
) -> None:
    assert effective_min_algo_confluence(3, available) == expected
