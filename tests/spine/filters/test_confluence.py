import logging
from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.indicators.schemas import (
    BollingerBandsSchema,
    TechnicalIndicatorsSchema,
    VolumeAnalysisSchema,
)
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator


def test_confluence_score(
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    calculator = ConfluenceCalculator()

    result = calculator.evaluate(
        side="LONG",
        candle=sample_candle,
        indicators=sample_indicators,
        order_flow=sample_order_flow,
    )

    # EMA aligned LONG (101>100>98), trend-mode RSI needs 50-70 but RSI=35 → False
    assert result.score == 3, "Expected confluence score to match signals"
    assert result.ema_alignment is True, "Expected EMA alignment"
    assert result.rsi_favorable is False, "Trend-mode LONG RSI 35 not in 50-70"
    assert result.volume_above_average is True, "Expected volume above average"
    assert result.price_at_bollinger is False, "Expected not at lower band"
    assert result.funding_favorable is False, "Expected funding not favorable"
    assert result.oi_supports_direction is True, "Expected OI to support direction"
    assert result.volume_spike is False, "Volume ratio 1.2 not > 2.5"


def test_confluence_short_funding(
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    calculator = ConfluenceCalculator()
    order_flow = sample_order_flow.model_copy(
        update={
            "funding_zscore": Decimal("1.0"),
            "oi_change_1h_percent": Decimal(-1),
        },
    )

    result = calculator.evaluate(
        side="SHORT",
        candle=sample_candle,
        indicators=sample_indicators,
        order_flow=order_flow,
    )

    assert result.funding_favorable is True, "Expected funding favorable for short"
    assert result.oi_supports_direction is True, "Expected OI to support short"


def test_rsi_favorable_trend_mode_short(
    sample_candle,
    sample_order_flow,
) -> None:
    """When EMAs are bearish-aligned, RSI 50-70 is favorable for SHORT."""
    now = datetime.now(UTC)
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(98),
        ema_50=Decimal(100),
        ema_200=Decimal(102),
        sma_20=Decimal(100),
        rsi_14=Decimal(60),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal(1200),
            average_volume=Decimal(1000),
            volume_ratio=Decimal("1.2"),
            obv=None,
        ),
        timestamp=now,
    )
    calculator = ConfluenceCalculator()

    result = calculator.evaluate(
        side="SHORT",
        candle=sample_candle,
        indicators=indicators,
        order_flow=sample_order_flow,
    )

    assert result.ema_alignment is True, "EMAs bearish-aligned"
    assert result.rsi_favorable is True, "RSI 60 in trend-mode SHORT range 50-70"


def test_rsi_favorable_reversal_mode_short(
    sample_candle,
    sample_order_flow,
) -> None:
    """Without EMA alignment, RSI 40 is NOT favorable for SHORT (needs 60-70)."""
    now = datetime.now(UTC)
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(101),
        ema_50=Decimal(100),
        ema_200=Decimal(98),
        sma_20=Decimal(100),
        rsi_14=Decimal(40),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal(1200),
            average_volume=Decimal(1000),
            volume_ratio=Decimal("1.2"),
            obv=None,
        ),
        timestamp=now,
    )
    calculator = ConfluenceCalculator()

    result = calculator.evaluate(
        side="SHORT",
        candle=sample_candle,
        indicators=indicators,
        order_flow=sample_order_flow,
    )

    assert result.ema_alignment is False, "EMAs not bearish-aligned"
    assert result.rsi_favorable is False, "RSI 40 not in reversal SHORT range 60-70"


def test_bollinger_walks_band_short(
    sample_order_flow,
) -> None:
    """SHORT with bearish EMAs + price at lower band = walks the band (True)."""
    now = datetime.now(UTC)
    from kavzi_trader.api.common.models import CandlestickSchema

    candle = CandlestickSchema(
        open_time=now,
        open_price=Decimal(96),
        high_price=Decimal(97),
        low_price=Decimal(94),
        close_price=Decimal(94),
        volume=Decimal(1000),
        close_time=now,
        quote_volume=Decimal(100000),
        trades_count=100,
        taker_buy_base_volume=Decimal(500),
        taker_buy_quote_volume=Decimal(50000),
        interval="5m",
        symbol="BTCUSDT",
    )
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(98),
        ema_50=Decimal(100),
        ema_200=Decimal(102),
        sma_20=Decimal(100),
        rsi_14=Decimal(35),
        macd=None,
        bollinger=BollingerBandsSchema(
            upper=Decimal(110),
            middle=Decimal(100),
            lower=Decimal(95),
            width=Decimal("0.1"),
            percent_b=Decimal("0.1"),
        ),
        atr_14=Decimal(5),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal(1200),
            average_volume=Decimal(1000),
            volume_ratio=Decimal("1.2"),
            obv=None,
        ),
        timestamp=now,
    )
    calculator = ConfluenceCalculator()

    result = calculator.evaluate(
        side="SHORT",
        candle=candle,
        indicators=indicators,
        order_flow=sample_order_flow,
    )

    assert result.ema_alignment is True, "EMAs bearish-aligned"
    assert result.price_at_bollinger is True, "Price at lower band + bearish EMAs"


def test_volume_spike(
    sample_candle,
    sample_order_flow,
) -> None:
    """Volume ratio > 2.5 triggers volume_spike signal."""
    now = datetime.now(UTC)
    indicators_spike = TechnicalIndicatorsSchema(
        ema_20=Decimal(101),
        ema_50=Decimal(100),
        ema_200=Decimal(98),
        sma_20=Decimal(100),
        rsi_14=Decimal(50),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal(3000),
            average_volume=Decimal(1000),
            volume_ratio=Decimal("3.0"),
            obv=None,
        ),
        timestamp=now,
    )
    indicators_normal = TechnicalIndicatorsSchema(
        ema_20=Decimal(101),
        ema_50=Decimal(100),
        ema_200=Decimal(98),
        sma_20=Decimal(100),
        rsi_14=Decimal(50),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal(2000),
            average_volume=Decimal(1000),
            volume_ratio=Decimal("2.0"),
            obv=None,
        ),
        timestamp=now,
    )
    calculator = ConfluenceCalculator()

    result_spike = calculator.evaluate(
        side="LONG",
        candle=sample_candle,
        indicators=indicators_spike,
        order_flow=sample_order_flow,
    )
    result_normal = calculator.evaluate(
        side="LONG",
        candle=sample_candle,
        indicators=indicators_normal,
        order_flow=sample_order_flow,
    )

    assert result_spike.volume_spike is True, "Volume ratio 3.0 > 2.5"
    assert result_normal.volume_spike is False, "Volume ratio 2.0 not > 2.5"


def test_no_warning_for_non_detected_side_zero_score(
    sample_candle,
    caplog,
) -> None:
    """When the non-detected side scores 0, no warning should be emitted."""
    now = datetime.now(UTC)
    # All None indicators → every signal returns False → score 0 for both sides
    indicators = TechnicalIndicatorsSchema(
        ema_20=None,
        ema_50=None,
        ema_200=None,
        sma_20=None,
        rsi_14=None,
        macd=None,
        bollinger=None,
        atr_14=None,
        volume=None,
        timestamp=now,
    )
    calculator = ConfluenceCalculator()

    with caplog.at_level(
        logging.WARNING, logger="kavzi_trader.spine.filters.confluence"
    ):
        # Evaluate only the non-detected side (SHORT) when detected is LONG
        calculator.evaluate(
            "SHORT",
            sample_candle,
            indicators,
            None,
            is_detected_side=False,
        )

    warning_messages = [
        r.message for r in caplog.records if r.levelno >= logging.WARNING
    ]
    assert not warning_messages, (
        f"Expected no warning for non-detected side, got: {warning_messages}"
    )


def test_warning_for_detected_side_zero_score(
    sample_candle,
    caplog,
) -> None:
    """When the detected side scores 0, a warning should be emitted."""
    now = datetime.now(UTC)
    indicators = TechnicalIndicatorsSchema(
        ema_20=None,
        ema_50=None,
        ema_200=None,
        sma_20=None,
        rsi_14=None,
        macd=None,
        bollinger=None,
        atr_14=None,
        volume=None,
        timestamp=now,
    )
    calculator = ConfluenceCalculator()

    with caplog.at_level(
        logging.WARNING, logger="kavzi_trader.spine.filters.confluence"
    ):
        calculator.evaluate(
            "LONG",
            sample_candle,
            indicators,
            None,
            is_detected_side=True,
        )

    warning_messages = [
        r.message for r in caplog.records if r.levelno >= logging.WARNING
    ]
    assert any("detected side" in msg for msg in warning_messages), (
        f"Expected warning for detected side with score 0, got: {warning_messages}"
    )


def test_volume_spike_suppresses_volume_above_average(
    sample_candle,
    sample_order_flow,
) -> None:
    """When volume_spike fires, volume_above_average must be suppressed."""
    now = datetime.now(UTC)
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(101),
        ema_50=Decimal(100),
        ema_200=Decimal(98),
        sma_20=Decimal(100),
        rsi_14=Decimal(50),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal(3000),
            average_volume=Decimal(1000),
            volume_ratio=Decimal("3.0"),
            obv=None,
        ),
        timestamp=now,
    )
    calculator = ConfluenceCalculator()

    result = calculator.evaluate(
        side="LONG",
        candle=sample_candle,
        indicators=indicators,
        order_flow=sample_order_flow,
    )

    assert result.volume_spike is True, "Volume ratio 3.0 > 2.5 triggers spike"
    assert result.volume_above_average is False, (
        "volume_above_average must be suppressed when volume_spike is active"
    )


def test_volume_above_average_fires_without_spike(
    sample_candle,
    sample_order_flow,
) -> None:
    """volume_above_average fires normally when volume is below spike threshold."""
    now = datetime.now(UTC)
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(101),
        ema_50=Decimal(100),
        ema_200=Decimal(98),
        sma_20=Decimal(100),
        rsi_14=Decimal(50),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal(1500),
            average_volume=Decimal(1000),
            volume_ratio=Decimal("1.5"),
            obv=None,
        ),
        timestamp=now,
    )
    calculator = ConfluenceCalculator()

    result = calculator.evaluate(
        side="LONG",
        candle=sample_candle,
        indicators=indicators,
        order_flow=sample_order_flow,
    )

    assert result.volume_spike is False, "Volume ratio 1.5 not > 2.5"
    assert result.volume_above_average is True, (
        "volume_above_average should fire when spike is not active"
    )


def test_no_volume_double_counting_in_score(
    sample_candle,
) -> None:
    """With a volume spike, total score must not double-count volume signals."""
    now = datetime.now(UTC)
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(101),
        ema_50=Decimal(100),
        ema_200=Decimal(98),
        sma_20=Decimal(100),
        rsi_14=Decimal(55),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal(3000),
            average_volume=Decimal(1000),
            volume_ratio=Decimal("3.0"),
            obv=None,
        ),
        timestamp=now,
    )
    calculator = ConfluenceCalculator()

    result = calculator.evaluate(
        side="LONG",
        candle=sample_candle,
        indicators=indicators,
        order_flow=None,
    )

    # ema_alignment=True, rsi_favorable=True (55 in 50-70 trend-mode),
    # volume_spike=True, volume_above_average=False (suppressed),
    # all others False (no bollinger, no order_flow)
    assert result.volume_spike is True
    assert result.volume_above_average is False
    assert result.score == 3, (
        f"Expected score=3 (ema + rsi + spike), got {result.score}"
    )
