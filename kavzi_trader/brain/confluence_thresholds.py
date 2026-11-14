# Confluence hysteresis bands for Analyst verdicts.
#
# The router requires confluence >= the regime-specific entry gate to
# escalate to the Trader tier. The reasoning loop treats scores in the
# borderline band (CONFLUENCE_REJECT_MAX+1 to gate-1) as "wait for a new
# bar" rather than "aggressive rejection". Bar-close dedup in the router
# prevents flip-flop by memoizing the Analyst verdict within the same bar.
#
# Lives in the Brain layer (not orchestrator) because it encodes the
# Brain's escalation policy and is consumed by the context builder, agent
# factory, and router. Keeping it here avoids a Brain->orchestrator import
# inversion that would drag the eager orchestrator package init into every
# brain import and create a circular import.
from kavzi_trader.domain.algorithm_confluence import (
    ALGO_SIGNAL_COUNT,
    MAX_DISCRETIONARY_POINTS,
)
from kavzi_trader.domain.volatility_regime import VolatilityRegime

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


# Extra raw points a setup needs when it fights the 1h trend.
COUNTER_TREND_GATE_BUMP = 1


def all_regime_gates() -> dict[VolatilityRegime, int]:
    """Return every regime's entry gate, for rendering into prompts."""
    return dict(_REGIME_ENTER_MIN)


def confluence_enter_min_for_regime(regime: VolatilityRegime) -> int:
    """Return the minimum raw confluence score required to escalate to Trader."""
    return _REGIME_ENTER_MIN[regime]


def _scale_gate(base_gate: int, available_signals: int) -> int:
    """Shrink a gate in proportion to the reachable maximum, rounding up."""
    if not 0 <= available_signals <= ALGO_SIGNAL_COUNT:
        raise ValueError(
            f"available_signals must be in 0..{ALGO_SIGNAL_COUNT},"
            f" got {available_signals}"
        )
    full_max = ALGO_SIGNAL_COUNT + MAX_DISCRETIONARY_POINTS
    reachable_max = available_signals + MAX_DISCRETIONARY_POINTS
    return -(-base_gate * reachable_max // full_max)


def effective_regime_gate(regime: VolatilityRegime, available_signals: int) -> int:
    """Regime gate scaled down when some algorithm signals have no input."""
    return _scale_gate(confluence_enter_min_for_regime(regime), available_signals)


def effective_min_algo_confluence(
    min_algo_confluence: int,
    available_signals: int,
) -> int:
    """Analyst pre-filter threshold, lowered by the NORMAL gate's scaling."""
    reduction = CONFLUENCE_ENTER_MIN - effective_regime_gate(
        VolatilityRegime.NORMAL, available_signals
    )
    return max(0, min_algo_confluence - reduction)
