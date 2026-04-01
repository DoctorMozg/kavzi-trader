from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.brain.context.formatters import (
    _price_based_precision,
    format_indicators_compact,
)
from kavzi_trader.indicators.schemas import (
    BollingerBandsSchema,
    MACDResultSchema,
    TechnicalIndicatorsSchema,
    VolumeAnalysisSchema,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _make_indicators(
    *,
    atr: Decimal = Decimal("0.0003"),
    ema_20: Decimal = Decimal("0.1800"),
    bb_width: Decimal = Decimal("0.0020"),
) -> TechnicalIndicatorsSchema:
    return TechnicalIndicatorsSchema(
        ema_20=ema_20,
        ema_50=Decimal("0.1750"),
        ema_200=Decimal("0.1600"),
        sma_20=Decimal("0.1790"),
        rsi_14=Decimal("55.3"),
        atr_14=atr,
        macd=MACDResultSchema(
            macd_line=Decimal("0.00012"),
            signal_line=Decimal("0.00008"),
            histogram=Decimal("0.00004"),
        ),
        bollinger=BollingerBandsSchema(
            upper=Decimal("0.1900"),
            middle=Decimal("0.1800"),
            lower=Decimal("0.1700"),
            width=bb_width,
            percent_b=Decimal("0.55"),
        ),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal(1000),
            average_volume=Decimal(1000),
            volume_ratio=Decimal("1.2"),
            obv=None,
        ),
        timestamp=_NOW,
    )


class TestPriceBasedPrecision:
    def test_high_price_returns_2(self) -> None:
        assert _price_based_precision(Decimal(68000)) == 2

    def test_mid_price_returns_4(self) -> None:
        assert _price_based_precision(Decimal("1.22")) == 4

    def test_low_price_returns_6(self) -> None:
        assert _price_based_precision(Decimal("0.18")) == 6

    def test_boundary_1000_returns_2(self) -> None:
        assert _price_based_precision(Decimal(1000)) == 2

    def test_boundary_1_returns_4(self) -> None:
        assert _price_based_precision(Decimal(1)) == 4

    def test_below_1_returns_6(self) -> None:
        assert _price_based_precision(Decimal("0.99")) == 6


class TestFormatIndicatorsCompact:
    def test_low_price_atr_not_rounded_to_zero(self) -> None:
        """ATR=0.0003 at price $0.18 must NOT show as 0.00."""
        ind = _make_indicators(atr=Decimal("0.0003"))
        result = format_indicators_compact(ind, reference_price=Decimal("0.18"))
        assert "ATR=0.000300" in result

    def test_high_price_atr_uses_2_decimals(self) -> None:
        ind = TechnicalIndicatorsSchema(
            ema_20=Decimal(68100),
            ema_50=Decimal(67500),
            ema_200=Decimal(60000),
            sma_20=Decimal(68000),
            rsi_14=Decimal("55.0"),
            atr_14=Decimal("180.55"),
            timestamp=_NOW,
        )
        result = format_indicators_compact(ind, reference_price=Decimal(68000))
        assert "ATR=180.55" in result

    def test_mid_price_uses_4_decimals(self) -> None:
        ind = _make_indicators(
            atr=Decimal("0.0029"),
            ema_20=Decimal("1.2200"),
        )
        result = format_indicators_compact(ind, reference_price=Decimal("1.22"))
        assert "ATR=0.0029" in result
        assert "EMA20=1.2200" in result

    def test_bb_width_always_4_decimals(self) -> None:
        ind = _make_indicators(bb_width=Decimal("0.002"))
        result = format_indicators_compact(ind, reference_price=Decimal("0.18"))
        assert "w=0.0020" in result

    def test_bb_percent_b_keeps_2_decimals(self) -> None:
        ind = _make_indicators()
        result = format_indicators_compact(ind, reference_price=Decimal("0.18"))
        assert "%B=0.55" in result

    def test_no_reference_price_falls_back_to_2(self) -> None:
        """Backward compat: no reference_price uses precision=2."""
        ind = TechnicalIndicatorsSchema(
            atr_14=Decimal("180.55"),
            rsi_14=Decimal("50.0"),
            timestamp=_NOW,
        )
        result = format_indicators_compact(ind)
        assert "ATR=180.55" in result

    def test_macd_uses_price_precision(self) -> None:
        ind = _make_indicators()
        result = format_indicators_compact(ind, reference_price=Decimal("0.18"))
        assert "MACD=0.000120" in result
