import logging
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.schemas.dependencies import ScoutDependenciesSchema
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.spine.filters.scout_config import ScoutConfigSchema

logger = logging.getLogger(__name__)

_ZERO = Decimal(0)


class _ScoutCriterionResult(BaseModel):
    verdict: Literal["INTERESTING", "SKIP"]
    reason: str
    pattern_detected: str | None = None
    model_config = ConfigDict(frozen=True)


_CRITERION_SKIP = _ScoutCriterionResult(verdict="SKIP", reason="")


class _GateOutcomeSchema(BaseModel):
    """Result of a single scout gate.

    ``passed=True`` means the gate did not reject the candidate.  For the
    terminal pattern gate, ``matched`` carries the criterion that fired
    (``None`` only while the non-terminal gates are still evaluating).
    ``reason`` is populated when a gate rejects and bubbles into the final
    ``ScoutDecisionSchema``.
    """

    passed: bool
    reason: str | None = None
    matched: _ScoutCriterionResult | None = None
    model_config = ConfigDict(frozen=True)


_GATE_PASS = _GateOutcomeSchema(passed=True)


class ScoutFilter:
    """Deterministic pattern filter replacing the LLM-based Scout agent.

    Checks six technical criteria against pre-computed indicators.
    Satisfies the ``ScoutRunner`` protocol used by ``AgentRouter``.
    """

    def __init__(self, config: ScoutConfigSchema) -> None:
        self._cfg = config

    # ------------------------------------------------------------------
    # Public interface (satisfies ScoutRunner protocol)
    # ------------------------------------------------------------------

    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        result = self._evaluate(deps)
        logger.info(
            "Scout result for %s: verdict=%s reason=%s pattern=%s",
            deps.symbol,
            result.verdict,
            result.reason,
            result.pattern_detected,
            extra={"symbol": deps.symbol},
        )
        return result

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def _evaluate(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        regime_outcome = self._check_regime_gate(deps)
        if not regime_outcome.passed:
            return ScoutDecisionSchema(
                verdict="SKIP",
                reason=regime_outcome.reason or "",
                pattern_detected=None,
            )

        atr_outcome = self._check_atr_gate(deps)
        if not atr_outcome.passed:
            return ScoutDecisionSchema(
                verdict="SKIP",
                reason=atr_outcome.reason or "",
                pattern_detected=None,
            )

        volume_outcome = self._check_volume_gates(deps)
        if not volume_outcome.passed:
            return ScoutDecisionSchema(
                verdict="SKIP",
                reason=volume_outcome.reason or "",
                pattern_detected=None,
            )

        pattern_outcome = self._check_pattern_criteria(deps)
        if not pattern_outcome.passed:
            return ScoutDecisionSchema(
                verdict="SKIP",
                reason=pattern_outcome.reason or "",
                pattern_detected=None,
            )
        matched = pattern_outcome.matched
        if matched is None:
            # Contract of _check_pattern_criteria: passed=True implies matched.
            raise RuntimeError("pattern gate passed without a matched criterion")
        return ScoutDecisionSchema(
            verdict="INTERESTING",
            reason=matched.reason,
            pattern_detected=matched.pattern_detected,
        )

    # ------------------------------------------------------------------
    # Gate methods
    # ------------------------------------------------------------------

    def _check_regime_gate(
        self,
        deps: ScoutDependenciesSchema,
    ) -> _GateOutcomeSchema:
        """Volatility regime gate (TIER_1 allowed through EXTREME)."""
        cfg = self._cfg
        regime = deps.volatility_regime.value
        tier1_extreme = regime == "EXTREME" and deps.symbol_tier == "TIER_1"
        blocked = regime in cfg.blocked_regimes and not tier1_extreme
        extreme_pattern_gate = (
            blocked and regime == "EXTREME" and bool(cfg.extreme_allowed_patterns)
        )

        # Non-EXTREME blocked regimes (LOW) short-circuit immediately.
        # EXTREME with allowed_patterns falls through to criteria checks.
        if blocked and not extreme_pattern_gate:
            return _GateOutcomeSchema(
                passed=False,
                reason=f"Volatility regime {regime} blocks trading",
            )
        return _GATE_PASS

    def _check_atr_gate(
        self,
        deps: ScoutDependenciesSchema,
    ) -> _GateOutcomeSchema:
        """ATR compression gate (adaptive per-symbol).

        Reject symbols where ATR is too small relative to price for viable
        stop-loss placement.  Threshold is max(floor, percentile of the
        symbol's own ATR% history) so quiet large-caps are not categorically
        blocked at a fixed global floor (see report_2026_04_05 Priority 3).
        """
        atr_pct = self._atr_pct(deps.indicators, deps.current_price)
        if atr_pct is None:
            return _GATE_PASS
        threshold = self._effective_atr_threshold(deps.atr_pct_history)
        if atr_pct < threshold:
            return _GateOutcomeSchema(
                passed=False,
                reason=(
                    f"ATR compressed (atr_pct={atr_pct:.4f}%,"
                    f" threshold={threshold:.4f}%)"
                ),
            )
        return _GATE_PASS

    def _check_volume_gates(
        self,
        deps: ScoutDependenciesSchema,
    ) -> _GateOutcomeSchema:
        """Hard volume floor (soft gate applied inside the pattern gate)."""
        cfg = self._cfg
        vol_ratio = self._vol_ratio(deps.indicators)
        if vol_ratio is not None and vol_ratio < cfg.vol_ratio_hard_skip:
            return _GateOutcomeSchema(
                passed=False,
                reason=(
                    f"Volume too low (ratio={vol_ratio},"
                    f" threshold={cfg.vol_ratio_hard_skip})"
                ),
            )
        return _GATE_PASS

    def _check_pattern_criteria(
        self,
        deps: ScoutDependenciesSchema,
    ) -> _GateOutcomeSchema:
        """Run the six pattern criteria plus the soft-volume fallback.

        Returns ``passed=True`` with ``matched`` set to the first criterion
        that fires (respecting the EXTREME allowed-pattern list).  Returns
        ``passed=False`` when either the soft-volume floor is breached or
        no criterion matches.
        """
        cfg = self._cfg
        ind = deps.indicators
        regime = deps.volatility_regime.value
        tier1_extreme = regime == "EXTREME" and deps.symbol_tier == "TIER_1"
        blocked = regime in cfg.blocked_regimes and not tier1_extreme
        extreme_pattern_gate = (
            blocked and regime == "EXTREME" and bool(cfg.extreme_allowed_patterns)
        )
        vol_ratio = self._vol_ratio(ind)
        alignment = self._ema_alignment(ind)
        candles = deps.recent_candles

        checks = [
            self._check_breakout(ind, vol_ratio),
            self._check_trend_continuation(ind, vol_ratio, alignment),
            self._check_reversal(ind),
            self._check_volume_spike(ind, vol_ratio, candles, alignment),
            self._check_momentum_shift(ind, candles),
            self._check_trend_pullback(candles, alignment),
        ]

        for check in checks:
            if check.verdict == "INTERESTING":
                if (
                    extreme_pattern_gate
                    and check.pattern_detected not in cfg.extreme_allowed_patterns
                ):
                    continue
                return _GateOutcomeSchema(passed=True, matched=check)

        # --- Soft volume gate (no criterion matched) ---
        if vol_ratio is not None and vol_ratio < cfg.vol_ratio_soft_skip:
            return _GateOutcomeSchema(
                passed=False,
                reason=(
                    f"Low volume (ratio={vol_ratio},"
                    f" soft threshold={cfg.vol_ratio_soft_skip})"
                    " and no pattern detected"
                ),
            )

        return _GateOutcomeSchema(passed=False, reason="No pattern detected")

    # ------------------------------------------------------------------
    # Criteria
    # ------------------------------------------------------------------

    def _check_breakout(
        self,
        ind: TechnicalIndicatorsSchema,
        vol_ratio: Decimal | None,
    ) -> _ScoutCriterionResult:
        """Criterion 1: price beyond Bollinger Band with volume."""
        cfg = self._cfg
        bb = ind.bollinger
        if bb is None or vol_ratio is None:
            return _CRITERION_SKIP
        if vol_ratio < cfg.breakout_vol_ratio_min:
            return _CRITERION_SKIP
        margin = cfg.breakout_percent_b_margin_min
        if bb.percent_b >= (Decimal(1) + margin) or bb.percent_b <= (_ZERO - margin):
            return _ScoutCriterionResult(
                verdict="INTERESTING",
                reason=(
                    f"Criterion 1 BREAKOUT: %B={bb.percent_b}, vol_ratio={vol_ratio}"
                ),
                pattern_detected="BREAKOUT",
            )
        return _CRITERION_SKIP

    def _check_trend_continuation(
        self,
        ind: TechnicalIndicatorsSchema,
        vol_ratio: Decimal | None,
        alignment: str,
    ) -> _ScoutCriterionResult:
        """Criterion 2: EMA alignment + RSI mid-range + volume."""
        cfg = self._cfg
        if alignment == "NEUTRAL":
            return _CRITERION_SKIP
        rsi = ind.rsi_14
        if rsi is None or vol_ratio is None:
            return _CRITERION_SKIP
        if not (cfg.trend_rsi_low <= rsi <= cfg.trend_rsi_high):
            return _CRITERION_SKIP
        if vol_ratio < cfg.trend_vol_ratio_min:
            return _CRITERION_SKIP
        return _ScoutCriterionResult(
            verdict="INTERESTING",
            reason=(
                f"Criterion 2 TREND_CONTINUATION:"
                f" {alignment} EMA alignment, RSI={rsi},"
                f" vol_ratio={vol_ratio}"
            ),
            pattern_detected="TREND_CONTINUATION",
        )

    def _check_reversal(
        self,
        ind: TechnicalIndicatorsSchema,
    ) -> _ScoutCriterionResult:
        """Criterion 3: RSI extreme + price at BB boundary."""
        cfg = self._cfg
        rsi = ind.rsi_14
        bb = ind.bollinger
        if rsi is None or bb is None:
            return _CRITERION_SKIP
        rsi_extreme = (
            rsi < cfg.reversal_rsi_oversold or rsi > cfg.reversal_rsi_overbought
        )
        bb_boundary = (
            bb.percent_b < cfg.reversal_percent_b_lower
            or bb.percent_b > cfg.reversal_percent_b_upper
        )
        if rsi_extreme and bb_boundary:
            return _ScoutCriterionResult(
                verdict="INTERESTING",
                reason=f"Criterion 3 REVERSAL: RSI={rsi}, %B={bb.percent_b}",
                pattern_detected="REVERSAL",
            )
        return _CRITERION_SKIP

    def _check_volume_spike(
        self,
        ind: TechnicalIndicatorsSchema,
        vol_ratio: Decimal | None,
        candles: list[CandlestickSchema],
        alignment: str,
    ) -> _ScoutCriterionResult:
        """Criterion 4: volume spike + large body + supporting signal."""
        cfg = self._cfg
        if vol_ratio is None or vol_ratio < cfg.volume_spike_ratio_min:
            return _CRITERION_SKIP
        if not candles:
            return _CRITERION_SKIP

        body_ratio = self._candle_body_ratio(candles[-1])
        if body_ratio < cfg.volume_spike_body_ratio_min:
            return _CRITERION_SKIP

        # At least one supporting signal required
        rsi = ind.rsi_14
        bb = ind.bollinger
        has_ema_support = alignment != "NEUTRAL"
        has_rsi_support = rsi is not None and (
            rsi < cfg.volume_spike_rsi_low or rsi > cfg.volume_spike_rsi_high
        )
        has_bb_support = bb is not None and (
            bb.percent_b < cfg.volume_spike_percent_b_lower
            or bb.percent_b > cfg.volume_spike_percent_b_upper
        )
        if not (has_ema_support or has_rsi_support or has_bb_support):
            return _CRITERION_SKIP

        support_parts: list[str] = []
        if has_ema_support:
            support_parts.append(f"EMA {alignment}")
        if has_rsi_support:
            support_parts.append(f"RSI={rsi}")
        if has_bb_support:
            support_parts.append(f"%B={bb.percent_b}")  # type: ignore[union-attr]
        return _ScoutCriterionResult(
            verdict="INTERESTING",
            reason=(
                f"Criterion 4 VOLUME_SPIKE: vol_ratio={vol_ratio},"
                f" body_ratio={body_ratio},"
                f" support=[{', '.join(support_parts)}]"
            ),
            pattern_detected="VOLUME_SPIKE",
        )

    def _check_momentum_shift(
        self,
        ind: TechnicalIndicatorsSchema,
        candles: list[CandlestickSchema],
    ) -> _ScoutCriterionResult:
        """Criterion 5: MACD histogram sign change.

        Since we only have a single indicator snapshot, we detect momentum
        shift by checking if the current MACD histogram sign differs from
        the price direction of the preceding candles.  All ``N-1``
        preceding candles (where N = ``momentum_min_candles``) must agree
        on the opposite direction to filter out single-candle noise.
        """
        cfg = self._cfg
        macd = ind.macd
        if macd is None or len(candles) < cfg.momentum_min_candles:
            return _CRITERION_SKIP

        histogram = macd.histogram
        histogram_bullish = histogram > _ZERO

        # Check that all (N-1) preceding candles had the opposite direction.
        lookback = cfg.momentum_min_candles - 1
        preceding = candles[-(lookback + 1) : -1]
        for c in preceding:
            direction = c.close_price - c.open_price
            if direction == _ZERO:
                return _CRITERION_SKIP
            if (direction > _ZERO) == histogram_bullish:
                # This candle agrees with the histogram → no shift
                return _CRITERION_SKIP

        shift_dir = "bullish" if histogram_bullish else "bearish"
        return _ScoutCriterionResult(
            verdict="INTERESTING",
            reason=(
                f"Criterion 5 MOMENTUM_SHIFT: histogram={histogram}"
                f" ({shift_dir}), prev {lookback} candle(s)"
                f" {'bearish' if histogram_bullish else 'bullish'}"
            ),
            pattern_detected="MOMENTUM_SHIFT",
        )

    def _check_trend_pullback(
        self,
        candles: list[CandlestickSchema],
        alignment: str,
    ) -> _ScoutCriterionResult:
        """Criterion 6: EMA aligned + meaningful price change + short-term momentum."""
        cfg = self._cfg
        if alignment == "NEUTRAL":
            return _CRITERION_SKIP
        pct = self._compute_price_change_pct(candles)
        if pct is None:
            return _CRITERION_SKIP

        # For BULLISH alignment, require positive change; for BEARISH, negative.
        trending = (alignment == "BULLISH" and pct > _ZERO) or (
            alignment == "BEARISH" and pct < _ZERO
        )
        if not trending or abs(pct) < cfg.pullback_price_change_min:
            return _CRITERION_SKIP

        # Verify recent candles confirm the trend direction to avoid
        # false positives where EMA alignment is stale but price is reversing.
        if not self._short_term_momentum_confirms(candles, alignment):
            return _CRITERION_SKIP

        return _ScoutCriterionResult(
            verdict="INTERESTING",
            reason=(
                f"Criterion 6 TREND_PULLBACK: {alignment} alignment, change={pct}%"
            ),
            pattern_detected="TREND_PULLBACK",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ema_alignment(self, ind: TechnicalIndicatorsSchema) -> str:
        if ind.ema_20 is None or ind.ema_50 is None or ind.ema_200 is None:
            return "NEUTRAL"
        if ind.ema_20 > ind.ema_50 > ind.ema_200:
            direction = "BULLISH"
        elif ind.ema_20 < ind.ema_50 < ind.ema_200:
            direction = "BEARISH"
        else:
            return "NEUTRAL"
        spread = abs(ind.ema_20 - ind.ema_200) / ind.ema_200 * 100
        if spread < self._cfg.ema_spread_min_pct:
            return "NEUTRAL"
        return direction

    def _short_term_momentum_confirms(
        self,
        candles: list[CandlestickSchema],
        alignment: str,
    ) -> bool:
        """Check that enough of the trailing close-to-close moves confirm trend.

        Window size and the required number of confirming moves are sourced
        from ``ScoutConfigSchema.short_term_momentum_window`` and
        ``short_term_momentum_min_confirming``.
        """
        cfg = self._cfg
        window = cfg.short_term_momentum_window
        if len(candles) < window:
            return True
        recent = candles[-window:]
        confirming = 0
        for i in range(1, len(recent)):
            if (
                alignment == "BULLISH"
                and recent[i].close_price >= recent[i - 1].close_price
            ) or (
                alignment == "BEARISH"
                and recent[i].close_price <= recent[i - 1].close_price
            ):
                confirming += 1
        return confirming >= cfg.short_term_momentum_min_confirming

    @staticmethod
    def _atr_pct(ind: TechnicalIndicatorsSchema, price: Decimal) -> Decimal | None:
        if ind.atr_14 is None or price == _ZERO:
            return None
        return ind.atr_14 / price * 100

    def _effective_atr_threshold(self, history: list[Decimal]) -> Decimal:
        """Return the adaptive ATR% threshold for the compression gate.

        Uses max(hard floor, configured percentile of the symbol's own
        recent ATR% history).  Falls back to the floor alone until the
        history reaches ``atr_pct_percentile_min_samples``.
        """
        cfg = self._cfg
        floor = cfg.atr_pct_min
        if len(history) < cfg.atr_pct_percentile_min_samples:
            return floor
        sorted_vals = sorted(history)
        # Percentile index: 0-indexed, clamped to the last sample.
        idx = int(len(sorted_vals) * cfg.atr_pct_percentile / Decimal(100))
        idx = min(idx, len(sorted_vals) - 1)
        percentile_val = sorted_vals[idx]
        return max(floor, percentile_val)

    @staticmethod
    def _vol_ratio(ind: TechnicalIndicatorsSchema) -> Decimal | None:
        if ind.volume is None:
            return None
        return ind.volume.volume_ratio

    @staticmethod
    def _candle_body_ratio(candle: CandlestickSchema) -> Decimal:
        high_low = candle.high_price - candle.low_price
        if high_low == _ZERO:
            return _ZERO
        body = abs(candle.close_price - candle.open_price)
        return body / high_low

    def _compute_price_change_pct(
        self,
        candles: list[CandlestickSchema],
    ) -> Decimal | None:
        if len(candles) < self._cfg.min_candles_for_change:
            return None
        first_close = candles[0].close_price
        if first_close == _ZERO:
            return None
        last_close = candles[-1].close_price
        return (last_close - first_close) / first_close * 100
