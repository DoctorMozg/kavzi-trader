# Confluence hysteresis bands for Analyst verdicts.
#
# The router requires confluence >= the regime-specific entry gate to
# escalate to the Trader tier. The reasoning loop treats scores in the
# borderline band (CONFLUENCE_REJECT_MAX+1 to gate-1) as "wait for a new
# bar" rather than "aggressive rejection". Bar-close dedup in the router
# prevents flip-flop by memoizing the Analyst verdict within the same bar.
from kavzi_trader.spine.risk.schemas import VolatilityRegime

CONFLUENCE_REJECT_MAX = 4  # score <= 4 → escalating rejection cooldown
CONFLUENCE_ENTER_MIN = 6  # NORMAL-regime alias; kept for legacy callers
# Scores in the range [CONFLUENCE_REJECT_MAX + 1, gate) form the borderline
# band: light cooldown, no counter escalation.

# Regime-specific entry gates. Replaces the prior prompt-side subtractive
# penalty model (-1 HIGH, -3 EXTREME) with explicit per-regime minimums
# applied to the raw Analyst confluence score. EXTREME stays tradeable if
# the setup is genuinely strong; NORMAL keeps behavioural parity with the
# legacy flat constant.
_REGIME_ENTER_MIN: dict[VolatilityRegime, int] = {
    VolatilityRegime.NORMAL: 6,
    VolatilityRegime.HIGH: 7,
    VolatilityRegime.EXTREME: 8,
    VolatilityRegime.LOW: 7,
}


def confluence_enter_min_for_regime(regime: VolatilityRegime) -> int:
    """Return the minimum raw confluence score required to escalate to Trader."""
    return _REGIME_ENTER_MIN[regime]
