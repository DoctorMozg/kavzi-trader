from decimal import Decimal

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

    assert result.score == 4, "Expected confluence score to match signals"
    assert result.ema_alignment is True, "Expected EMA alignment"
    assert result.rsi_favorable is True, "Expected RSI favorable"
    assert result.volume_above_average is True, "Expected volume above average"
    assert result.price_at_bollinger is False, "Expected not at lower band"
    assert result.funding_favorable is False, "Expected funding not favorable"
    assert result.oi_supports_direction is True, "Expected OI to support direction"


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
