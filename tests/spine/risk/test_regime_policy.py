from decimal import Decimal

import pytest

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from kavzi_trader.spine.risk.schemas import VolatilityRegime

_OVERRIDE_ON = RiskConfigSchema(extreme_high_confidence_pass=True)


class TestSizeMultiplier:
    @pytest.mark.parametrize(
        ("regime", "expected"),
        [
            (VolatilityRegime.LOW, Decimal(0)),
            (VolatilityRegime.NORMAL, Decimal("1.0")),
            (VolatilityRegime.HIGH, Decimal("0.5")),
        ],
    )
    def test_non_extreme_regimes_ignore_tier(
        self,
        regime: VolatilityRegime,
        expected: Decimal,
    ) -> None:
        policy = RegimePolicy(RiskConfigSchema())

        assert policy.size_multiplier(regime, "TIER_3") == expected

    def test_extreme_tier1_is_quarter_size(self) -> None:
        policy = RegimePolicy(RiskConfigSchema())

        assert policy.size_multiplier(VolatilityRegime.EXTREME, "TIER_1") == Decimal(
            "0.25",
        )

    @pytest.mark.parametrize("tier", ["TIER_2", "TIER_3"])
    def test_extreme_other_tiers_blocked_by_default(self, tier: str) -> None:
        policy = RegimePolicy(RiskConfigSchema())

        assert policy.size_multiplier(VolatilityRegime.EXTREME, tier) == Decimal(0)
        assert policy.size_multiplier(
            VolatilityRegime.EXTREME,
            tier,
            Decimal("0.99"),
        ) == Decimal(0)

    def test_confidence_override_needs_opt_in_and_threshold(self) -> None:
        policy = RegimePolicy(_OVERRIDE_ON)

        high = policy.size_multiplier(
            VolatilityRegime.EXTREME,
            "TIER_2",
            Decimal("0.80"),
        )
        low = policy.size_multiplier(
            VolatilityRegime.EXTREME,
            "TIER_2",
            Decimal("0.79"),
        )
        unknown = policy.size_multiplier(VolatilityRegime.EXTREME, "TIER_2")

        assert (high, low, unknown) == (Decimal("0.25"), Decimal(0), Decimal(0))


class TestScoutAdmission:
    def test_tier1_open_with_any_pattern(self) -> None:
        policy = RegimePolicy(RiskConfigSchema(), ["BREAKOUT"])

        assert policy.extreme_open_for_scout("TIER_1") is True
        assert policy.extreme_pattern_allowed("TIER_1", "REVERSAL") is True

    def test_other_tiers_closed_without_override_even_with_patterns(self) -> None:
        policy = RegimePolicy(RiskConfigSchema(), ["BREAKOUT"])

        assert policy.extreme_open_for_scout("TIER_2") is False
        assert policy.extreme_pattern_allowed("TIER_2", "BREAKOUT") is False

    def test_override_opens_only_listed_patterns(self) -> None:
        policy = RegimePolicy(_OVERRIDE_ON, ["BREAKOUT"])

        assert policy.extreme_open_for_scout("TIER_2") is True
        assert policy.extreme_pattern_allowed("TIER_2", "BREAKOUT") is True
        assert policy.extreme_pattern_allowed("TIER_2", "REVERSAL") is False

    def test_override_without_patterns_stays_closed_for_scout(self) -> None:
        policy = RegimePolicy(_OVERRIDE_ON, [])

        assert policy.extreme_open_for_scout("TIER_2") is False
