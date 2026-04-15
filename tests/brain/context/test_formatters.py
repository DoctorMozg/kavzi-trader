from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.context.formatters import (
    _price_based_precision,
    format_candles_table,
    format_indicators_compact,
    format_order_flow_compact,
)
from kavzi_trader.indicators.schemas import (
    BollingerBandsSchema,
    MACDResultSchema,
    TechnicalIndicatorsSchema,
    VolumeAnalysisSchema,
)
from kavzi_trader.order_flow.schemas import OrderFlowSchema

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


def _make_candle(open_time_iso: str) -> CandlestickSchema:
    when = datetime.fromisoformat(open_time_iso)
    return CandlestickSchema(
        open_time=when,
        close_time=when,
        open_price=Decimal(100),
        high_price=Decimal(101),
        low_price=Decimal("99.5"),
        close_price=Decimal("100.5"),
        volume=Decimal("12.3456"),
        quote_volume=Decimal("1234.56"),
        trades_count=42,
        taker_buy_base_volume=Decimal("6.0"),
        taker_buy_quote_volume=Decimal("600.0"),
    )


class TestFormatCandlesTable:
    # The Analyst prompt previously carried 9 columns per row
    # (time|O|H|L|C|V|quote_vol|trades|taker_buy_vol) of which only the
    # first six actually influenced rubric scoring. Trimmed to save ~300
    # tokens per Analyst request across the 12-candle window.

    def test_header_has_exactly_six_columns(self) -> None:
        table = format_candles_table([])
        assert table == "time|open|high|low|close|volume"
        assert table.count("|") == 5

    def test_row_has_exactly_six_columns(self) -> None:
        table = format_candles_table([_make_candle("2026-01-01T12:00:00")])
        header, row = table.split("\n")
        assert header.count("|") == 5
        assert row.count("|") == 5

    def test_row_omits_dropped_columns(self) -> None:
        table = format_candles_table([_make_candle("2026-01-01T12:00:00")])
        assert "quote_vol" not in table
        assert "trades" not in table
        assert "taker_buy" not in table
        # Dropped fields also must not leak their numeric values: the
        # quote_volume constant above (1234.56) would otherwise appear as a
        # substring if the row kept emitting it.
        assert "1234.56" not in table
        assert "|42|" not in table

    def test_row_keeps_ohlcv_data(self) -> None:
        table = format_candles_table([_make_candle("2026-01-01T12:00:00")])
        _, row = table.split("\n")
        # High-price-threshold candle uses 2-decimal precision per
        # _price_based_precision (close_price=100.5 is above the $1 mid
        # tier), so OHLC print with 4 decimals.
        assert row == "12:00|100.0000|101.0000|99.5000|100.5000|12.3456"


class TestFormatOrderFlowCompact:
    def test_format_order_flow_includes_squeeze_and_crowded(self) -> None:
        """Formatter must render squeeze_alert, is_crowded_long, is_crowded_short."""
        of = OrderFlowSchema(
            symbol="BTCUSDT",
            timestamp=_NOW,
            funding_rate=Decimal("0.0005"),
            funding_zscore=Decimal("2.5"),  # > 2.0 threshold -> crowded long
            next_funding_time=_NOW,
            open_interest=Decimal(100000),
            oi_change_1h_percent=Decimal("6.0"),  # > 5.0 threshold
            oi_change_24h_percent=Decimal("2.0"),
            long_short_ratio=Decimal("1.2"),
            long_account_percent=Decimal(60),
            short_account_percent=Decimal(40),
            price_change_1h_percent=Decimal("0.3"),  # < 0.5 threshold -> squeeze
        )
        result = format_order_flow_compact(of)

        assert result is not None
        assert "squeeze=True" in result
        assert "crowded_l=True" in result

    def test_format_order_flow_no_squeeze_no_crowded(self) -> None:
        """Normal conditions produce squeeze=False and crowded=False."""
        of = OrderFlowSchema(
            symbol="BTCUSDT",
            timestamp=_NOW,
            funding_rate=Decimal("0.0001"),
            funding_zscore=Decimal("0.5"),
            next_funding_time=_NOW,
            open_interest=Decimal(100000),
            oi_change_1h_percent=Decimal("1.0"),
            oi_change_24h_percent=Decimal("2.0"),
            long_short_ratio=Decimal("1.0"),
            long_account_percent=Decimal(50),
            short_account_percent=Decimal(50),
            price_change_1h_percent=Decimal("1.0"),
        )
        result = format_order_flow_compact(of)

        assert result is not None
        assert "squeeze=False" in result
        assert "crowded_l=False" in result
        assert "crowded_s=False" in result
