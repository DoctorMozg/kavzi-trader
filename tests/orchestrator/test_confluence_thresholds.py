import pytest

from kavzi_trader.orchestrator.loops.confluence_thresholds import (
    CONFLUENCE_ENTER_MIN,
    CONFLUENCE_REJECT_MAX,
    confluence_enter_min_for_regime,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime


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
