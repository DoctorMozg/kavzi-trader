import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Literal

from kavzi_trader.domain.decision_message import DecisionMessageSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.validation import ValidationOutcomeSchema
from kavzi_trader.spine.risk.schemas import RiskValidationResultSchema
from kavzi_trader.spine.risk.trade_validation_params_schema import (
    TradeValidationParamsSchema,
)
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager

_REGIME_SEVERITY = [
    VolatilityRegime.LOW,
    VolatilityRegime.NORMAL,
    VolatilityRegime.HIGH,
    VolatilityRegime.EXTREME,
]

logger = logging.getLogger(__name__)


class DecisionValidator:
    """Pre-execution checks: regime drift, staleness and risk."""

    def __init__(
        self,
        risk_validator: DynamicRiskValidator,
        staleness_checker: StalenessChecker,
        state_manager: StateManager,
        leverage_for: Callable[[str], int],
        volatility_detector: VolatilityRegimeDetector | None,
    ) -> None:
        self._risk_validator = risk_validator
        self._staleness_checker = staleness_checker
        self._state_manager = state_manager
        self._leverage_for = leverage_for
        self._volatility_detector = volatility_detector

    def validate_regime_drift(
        self,
        decision: DecisionMessageSchema,
    ) -> ValidationOutcomeSchema:
        """Resolve the volatility regime used for downstream staleness checks.

        Always passes. When a detector is wired and disagrees with the
        decision's regime, the stricter of the two is surfaced via
        ``extra["effective_regime"]``; otherwise the decision's own regime is
        returned verbatim.
        """
        effective_regime = decision.volatility_regime
        if self._volatility_detector is not None:
            detected = self._volatility_detector.detect_regime(
                decision.current_atr,
                decision.atr_history,
            )
            if detected.regime != decision.volatility_regime:
                logger.info(
                    "Regime drift for %s: decision=%s detected=%s, using stricter",
                    decision.symbol,
                    decision.volatility_regime.value,
                    detected.regime.value,
                )
                effective_regime = max(
                    decision.volatility_regime,
                    detected.regime,
                    key=lambda r: _REGIME_SEVERITY.index(r),
                )
        return ValidationOutcomeSchema(
            passed=True,
            reason=None,
            extra={"effective_regime": effective_regime},
        )

    def validate_staleness(
        self,
        decision: DecisionMessageSchema,
        regime: VolatilityRegime,
    ) -> ValidationOutcomeSchema:
        """Check decision freshness against regime-specific thresholds.

        Fails with reason ``"Decision expired"`` when the underlying
        ``StalenessChecker`` flags the decision as stale for the effective
        regime; this maps to an ``EXPIRED`` result in ``execute()``.
        """
        if self._staleness_checker.is_stale(
            decision.created_at_ms,
            regime,
        ):
            return ValidationOutcomeSchema(
                passed=False,
                reason="Decision expired",
                extra={"regime": regime.value},
            )
        return ValidationOutcomeSchema(passed=True, reason=None, extra=None)

    async def validate_risk(
        self,
        decision: DecisionMessageSchema,
    ) -> tuple[ValidationOutcomeSchema, RiskValidationResultSchema]:
        """Delegate to the risk validator and translate its verdict.

        Returns both the outcome (for the pipeline) and the raw validation
        result (so ``execute()`` can read ``recommended_size`` on success).
        """
        side: Literal["LONG", "SHORT"] = decision.action  # type: ignore[assignment]
        params = TradeValidationParamsSchema.model_validate(
            {
                "symbol": decision.symbol,
                "side": side,
                "entry_price": decision.entry_price,
                "stop_loss": decision.stop_loss,
                "take_profit": decision.take_profit,
                "current_atr": decision.current_atr,
                "atr_history": decision.atr_history,
                "leverage": self._leverage_for(decision.symbol),
                "confidence": Decimal(str(decision.calibrated_confidence)),
                "symbol_tier": decision.symbol_tier,
                "size_multiplier": decision.size_multiplier,
            },
        )
        result = await self._risk_validator.validate_trade(
            params,
            self._state_manager,
        )
        if not result.is_valid:
            return (
                ValidationOutcomeSchema(
                    passed=False,
                    reason="; ".join(result.rejection_reasons),
                    extra={"rejection_reasons": list(result.rejection_reasons)},
                ),
                result,
            )
        return ValidationOutcomeSchema(passed=True, reason=None, extra=None), result
