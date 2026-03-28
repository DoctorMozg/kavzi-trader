import logging
import time
from decimal import Decimal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.schemas.dependencies import ScoutDependenciesSchema
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.spine.filters.scout_config import ScoutConfigSchema

logger = logging.getLogger(__name__)

_ZERO = Decimal(0)
_MIN_CANDLES_FOR_CHANGE = 2


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
        t0 = time.monotonic()
        result = self._evaluate(deps)
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Scout result for %s: verdict=%s reason=%s pattern=%s elapsed_ms=%.1f",
            deps.symbol,
            result.verdict,
            result.reason,
            result.pattern_detected,
            elapsed_ms,
            extra={"symbol": deps.symbol, "elapsed_ms": round(elapsed_ms, 1)},
        )
        return result

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def _evaluate(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        cfg = self._cfg
        ind = deps.indicators
        regime = deps.volatility_regime.value

        # --- Volatility gate ---
        if regime in cfg.blocked_regimes:
            return ScoutDecisionSchema(
                verdict="SKIP",
                reason=f"Volatility regime {regime} blocks trading",
                pattern_detected=None,
            )

        # --- Volume gates ---
        vol_ratio = self._vol_ratio(ind)
        if vol_ratio is not None and vol_ratio < cfg.vol_ratio_hard_skip:
            return ScoutDecisionSchema(
                verdict="SKIP",
                reason=(
                    f"Volume too low (ratio={vol_ratio},"
                    f" threshold={cfg.vol_ratio_hard_skip})"
                ),
                pattern_detected=None,
            )

        # --- Criteria 1-6 (first match wins) ---
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

        for verdict, reason, pattern in checks:
            if verdict == "INTERESTING":
                return ScoutDecisionSchema(
                    verdict="INTERESTING",
                    reason=reason,
                    pattern_detected=pattern,
                )

        # --- Soft volume gate (no criterion matched) ---
        if vol_ratio is not None and vol_ratio < cfg.vol_ratio_soft_skip:
            return ScoutDecisionSchema(
                verdict="SKIP",
                reason=(
                    f"Low volume (ratio={vol_ratio},"
                    f" soft threshold={cfg.vol_ratio_soft_skip})"
                    " and no pattern detected"
                ),
                pattern_detected=None,
            )

        return ScoutDecisionSchema(
            verdict="SKIP",
            reason="No pattern detected",
            pattern_detected=None,
        )

    # ------------------------------------------------------------------
    # Criteria
    # ------------------------------------------------------------------

    def _check_breakout(
        self,
        ind: TechnicalIndicatorsSchema,
        vol_ratio: Decimal | None,
    ) -> tuple[str, str, str | None]:
        """Criterion 1: price beyond Bollinger Band with volume."""
        cfg = self._cfg
        bb = ind.bollinger
        if bb is None or vol_ratio is None:
            return ("SKIP", "", None)
        if vol_ratio < cfg.breakout_vol_ratio_min:
            return ("SKIP", "", None)
        if bb.percent_b >= Decimal(1) or bb.percent_b <= _ZERO:
            return (
                "INTERESTING",
                (f"Criterion 1 BREAKOUT: %B={bb.percent_b}, vol_ratio={vol_ratio}"),
                "BREAKOUT",
            )
        return ("SKIP", "", None)

    def _check_trend_continuation(
        self,
        ind: TechnicalIndicatorsSchema,
        vol_ratio: Decimal | None,
        alignment: str,
    ) -> tuple[str, str, str | None]:
        """Criterion 2: EMA alignment + RSI mid-range + volume."""
        cfg = self._cfg
        if alignment == "NEUTRAL":
            return ("SKIP", "", None)
        rsi = ind.rsi_14
        if rsi is None or vol_ratio is None:
            return ("SKIP", "", None)
        if not (cfg.trend_rsi_low <= rsi <= cfg.trend_rsi_high):
            return ("SKIP", "", None)
        if vol_ratio < cfg.trend_vol_ratio_min:
            return ("SKIP", "", None)
        return (
            "INTERESTING",
            (
                f"Criterion 2 TREND_CONTINUATION:"
                f" {alignment} EMA alignment, RSI={rsi},"
                f" vol_ratio={vol_ratio}"
            ),
            "TREND_CONTINUATION",
        )

    def _check_reversal(
        self,
        ind: TechnicalIndicatorsSchema,
    ) -> tuple[str, str, str | None]:
        """Criterion 3: RSI extreme + price at BB boundary."""
        cfg = self._cfg
        rsi = ind.rsi_14
        bb = ind.bollinger
        if rsi is None or bb is None:
            return ("SKIP", "", None)
        rsi_extreme = (
            rsi < cfg.reversal_rsi_oversold or rsi > cfg.reversal_rsi_overbought
        )
        bb_boundary = (
            bb.percent_b < cfg.reversal_percent_b_lower
            or bb.percent_b > cfg.reversal_percent_b_upper
        )
        if rsi_extreme and bb_boundary:
            return (
                "INTERESTING",
                (f"Criterion 3 REVERSAL: RSI={rsi}, %B={bb.percent_b}"),
                "REVERSAL",
            )
        return ("SKIP", "", None)

    def _check_volume_spike(
        self,
        ind: TechnicalIndicatorsSchema,
        vol_ratio: Decimal | None,
        candles: list[CandlestickSchema],
        alignment: str,
    ) -> tuple[str, str, str | None]:
        """Criterion 4: volume spike + large body + supporting signal."""
        cfg = self._cfg
        if vol_ratio is None or vol_ratio < cfg.volume_spike_ratio_min:
            return ("SKIP", "", None)
        if not candles:
            return ("SKIP", "", None)

        body_ratio = self._candle_body_ratio(candles[-1])
        if body_ratio < cfg.volume_spike_body_ratio_min:
            return ("SKIP", "", None)

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
            return ("SKIP", "", None)

        support_parts: list[str] = []
        if has_ema_support:
            support_parts.append(f"EMA {alignment}")
        if has_rsi_support:
            support_parts.append(f"RSI={rsi}")
        if has_bb_support:
            support_parts.append(f"%B={bb.percent_b}")  # type: ignore[union-attr]
        return (
            "INTERESTING",
            (
                f"Criterion 4 VOLUME_SPIKE: vol_ratio={vol_ratio},"
                f" body_ratio={body_ratio},"
                f" support=[{', '.join(support_parts)}]"
            ),
            "VOLUME_SPIKE",
        )

    def _check_momentum_shift(
        self,
        ind: TechnicalIndicatorsSchema,
        candles: list[CandlestickSchema],
    ) -> tuple[str, str, str | None]:
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
            return ("SKIP", "", None)

        histogram = macd.histogram
        histogram_bullish = histogram > _ZERO

        # Check that all (N-1) preceding candles had the opposite direction.
        lookback = cfg.momentum_min_candles - 1
        preceding = candles[-(lookback + 1) : -1]
        for c in preceding:
            direction = c.close_price - c.open_price
            if direction == _ZERO:
                return ("SKIP", "", None)
            if (direction > _ZERO) == histogram_bullish:
                # This candle agrees with the histogram → no shift
                return ("SKIP", "", None)

        shift_dir = "bullish" if histogram_bullish else "bearish"
        return (
            "INTERESTING",
            (
                f"Criterion 5 MOMENTUM_SHIFT: histogram={histogram}"
                f" ({shift_dir}), prev {lookback} candle(s)"
                f" {'bearish' if histogram_bullish else 'bullish'}"
            ),
            "MOMENTUM_SHIFT",
        )

    def _check_trend_pullback(
        self,
        candles: list[CandlestickSchema],
        alignment: str,
    ) -> tuple[str, str, str | None]:
        """Criterion 6: EMA aligned + meaningful price change."""
        cfg = self._cfg
        if alignment == "NEUTRAL":
            return ("SKIP", "", None)
        pct = self._compute_price_change_pct(candles)
        if pct is None:
            return ("SKIP", "", None)

        # For BULLISH alignment, require positive change; for BEARISH, negative.
        trending = (alignment == "BULLISH" and pct > _ZERO) or (
            alignment == "BEARISH" and pct < _ZERO
        )
        if trending and abs(pct) >= cfg.pullback_price_change_min:
            return (
                "INTERESTING",
                (f"Criterion 6 TREND_PULLBACK: {alignment} alignment, change={pct}%"),
                "TREND_PULLBACK",
            )
        return ("SKIP", "", None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ema_alignment(ind: TechnicalIndicatorsSchema) -> str:
        if ind.ema_20 is None or ind.ema_50 is None or ind.ema_200 is None:
            return "NEUTRAL"
        if ind.ema_20 > ind.ema_50 > ind.ema_200:
            return "BULLISH"
        if ind.ema_20 < ind.ema_50 < ind.ema_200:
            return "BEARISH"
        return "NEUTRAL"

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

    @staticmethod
    def _compute_price_change_pct(
        candles: list[CandlestickSchema],
    ) -> Decimal | None:
        if len(candles) < _MIN_CANDLES_FOR_CHANGE:
            return None
        first_close = candles[0].close_price
        if first_close == _ZERO:
            return None
        last_close = candles[-1].close_price
        return (last_close - first_close) / first_close * 100
