from collections.abc import Sequence
from decimal import Decimal

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.risk.symbol_tier import SymbolTier

_BASE_MULTIPLIERS: dict[VolatilityRegime, Decimal] = {
    VolatilityRegime.LOW: Decimal(0),
    VolatilityRegime.NORMAL: Decimal("1.0"),
    VolatilityRegime.HIGH: Decimal("0.5"),
    VolatilityRegime.EXTREME: Decimal(0),
}

_EXTREME_TIERS = frozenset({SymbolTier.TIER_1})
_EXTREME_MULTIPLIER = Decimal("0.25")


class RegimePolicy:
    """Single source for regime sizing and for who may trade in EXTREME.

    Scout, the filter chain, the detector and the validator all ask this class,
    so they cannot disagree about a symbol that is allowed through EXTREME.
    """

    def __init__(
        self,
        risk_config: RiskConfigSchema,
        extreme_allowed_patterns: Sequence[str] = (),
    ) -> None:
        self._risk_config = risk_config
        self._extreme_patterns = frozenset(extreme_allowed_patterns)

    def size_multiplier(
        self,
        regime: VolatilityRegime,
        symbol_tier: str = "TIER_2",
        confidence: Decimal | None = None,
    ) -> Decimal:
        if regime != VolatilityRegime.EXTREME:
            return _BASE_MULTIPLIERS[regime]
        if symbol_tier in _EXTREME_TIERS or self._confidence_override(confidence):
            return _EXTREME_MULTIPLIER
        return Decimal(0)

    def extreme_open_for_scout(self, symbol_tier: str) -> bool:
        """Whether Scout may look at candidates of this tier in EXTREME at all."""
        return symbol_tier in _EXTREME_TIERS or self._override_enabled_with_patterns()

    def extreme_pattern_allowed(self, symbol_tier: str, pattern: str | None) -> bool:
        if symbol_tier in _EXTREME_TIERS:
            return True
        return (
            self._override_enabled_with_patterns()
            and pattern is not None
            and pattern in self._extreme_patterns
        )

    def _override_enabled_with_patterns(self) -> bool:
        return self._risk_config.extreme_high_confidence_pass and bool(
            self._extreme_patterns,
        )

    def _confidence_override(self, confidence: Decimal | None) -> bool:
        cfg = self._risk_config
        return (
            cfg.extreme_high_confidence_pass
            and confidence is not None
            and confidence >= cfg.extreme_min_confidence_override
        )
