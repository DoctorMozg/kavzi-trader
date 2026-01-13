from decimal import Decimal

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector


class TestVolatilityRegimeDetector:
    def test_normal_regime_within_bounds(
        self,
        risk_config: RiskConfigSchema,
        atr_history_normal: list[Decimal],
    ) -> None:
        detector = VolatilityRegimeDetector(risk_config)
        result = detector.detect_regime(Decimal("100"), atr_history_normal)

        assert result.regime == VolatilityRegime.NORMAL
        assert result.is_tradeable is True
        assert result.size_multiplier == Decimal("1.0")

    def test_high_regime_detected(self, risk_config: RiskConfigSchema) -> None:
        detector = VolatilityRegimeDetector(risk_config)
        history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]
        result = detector.detect_regime(Decimal("105"), history)

        assert result.regime == VolatilityRegime.HIGH
        assert result.is_tradeable is True
        assert result.size_multiplier == Decimal("0.5")

    def test_extreme_regime_detected(self, risk_config: RiskConfigSchema) -> None:
        detector = VolatilityRegimeDetector(risk_config)
        history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]
        result = detector.detect_regime(Decimal("120"), history)

        assert result.regime == VolatilityRegime.EXTREME
        assert result.is_tradeable is False
        assert result.size_multiplier == Decimal("0")

    def test_low_regime_detected(self, risk_config: RiskConfigSchema) -> None:
        detector = VolatilityRegimeDetector(risk_config)
        history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]
        result = detector.detect_regime(Decimal("92"), history)

        assert result.regime == VolatilityRegime.LOW
        assert result.is_tradeable is False
        assert result.size_multiplier == Decimal("0")

    def test_insufficient_history_returns_normal(
        self,
        risk_config: RiskConfigSchema,
    ) -> None:
        detector = VolatilityRegimeDetector(risk_config)
        result = detector.detect_regime(Decimal("100"), [Decimal("100")])

        assert result.regime == VolatilityRegime.NORMAL
        assert result.atr_zscore == Decimal("0")

    def test_zero_std_returns_normal(self, risk_config: RiskConfigSchema) -> None:
        detector = VolatilityRegimeDetector(risk_config)
        history = [Decimal("100")] * 10
        result = detector.detect_regime(Decimal("100"), history)

        assert result.regime == VolatilityRegime.NORMAL
        assert result.atr_zscore == Decimal("0")

    def test_zscore_calculation_accuracy(self, risk_config: RiskConfigSchema) -> None:
        detector = VolatilityRegimeDetector(risk_config)
        history = [Decimal("90"), Decimal("100"), Decimal("110")]
        result = detector.detect_regime(Decimal("100"), history)

        assert result.atr_zscore == Decimal("0")

    def test_boundary_high_threshold(self) -> None:
        config = RiskConfigSchema(volatility_high_threshold=Decimal("1.0"))
        detector = VolatilityRegimeDetector(config)
        history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]

        result = detector.detect_regime(Decimal("104"), history)
        assert result.regime in (VolatilityRegime.NORMAL, VolatilityRegime.HIGH)
