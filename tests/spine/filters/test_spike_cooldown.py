from datetime import UTC, datetime, timedelta
from decimal import Decimal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.spike_cooldown import SpikeCooldownFilter


def _make_candle(
    open_price: Decimal,
    close_price: Decimal,
) -> CandlestickSchema:
    now = datetime(2025, 1, 6, 12, 0, tzinfo=UTC)
    return CandlestickSchema(
        open_time=now - timedelta(minutes=5),
        open_price=open_price,
        high_price=max(open_price, close_price) + Decimal(1),
        low_price=min(open_price, close_price) - Decimal(1),
        close_price=close_price,
        volume=Decimal(1000),
        close_time=now,
        quote_volume=Decimal(100000),
        trades_count=100,
        taker_buy_base_volume=Decimal(500),
        taker_buy_quote_volume=Decimal(50000),
        interval="5m",
        symbol="TONUSDT",
    )


def test_spike_blocks_chasing_long_after_bullish_spike() -> None:
    """LONG after bullish spike (chasing) should be rejected."""
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(120))  # bullish, body=20

    result = f.evaluate(candle=candle, atr=Decimal(10), side="LONG")  # ratio=2.0

    assert result.is_allowed is False
    assert "spike_detected" in (result.reason or "")
    assert "chasing LONG" in (result.reason or "")


def test_spike_allows_normal_candle() -> None:
    """Candle body < 1.5x ATR should pass regardless of side."""
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(105))  # body=5

    result = f.evaluate(candle=candle, atr=Decimal(10), side="LONG")  # ratio=0.5

    assert result.is_allowed is True
    assert result.reason is None


def test_spike_bypasses_when_atr_none() -> None:
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(120))

    result = f.evaluate(candle=candle, atr=None, side="LONG")

    assert result.is_allowed is True


def test_spike_bypasses_when_atr_zero() -> None:
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(120))

    result = f.evaluate(candle=candle, atr=Decimal(0), side="LONG")

    assert result.is_allowed is True


def test_spike_exact_threshold_passes() -> None:
    """Candle body exactly at threshold (1.5x ATR) should pass (> not >=)."""
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(115))  # body=15

    result = f.evaluate(candle=candle, atr=Decimal(10), side="LONG")  # ratio=1.5

    assert result.is_allowed is True


def test_spike_allows_reversal_short_after_bullish_spike() -> None:
    """SHORT after bullish spike is a reversal — should be allowed."""
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(120))  # bullish, body=20

    result = f.evaluate(candle=candle, atr=Decimal(10), side="SHORT")  # ratio=2.0

    assert result.is_allowed is True


def test_spike_allows_reversal_long_after_bearish_spike() -> None:
    """LONG after bearish spike is a reversal — should be allowed."""
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(120), Decimal(100))  # bearish, body=20

    result = f.evaluate(candle=candle, atr=Decimal(10), side="LONG")  # ratio=2.0

    assert result.is_allowed is True


def test_spike_blocks_chasing_short_after_bearish_spike() -> None:
    """SHORT after bearish spike (chasing) should be rejected."""
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(120), Decimal(100))  # bearish, body=20

    result = f.evaluate(candle=candle, atr=Decimal(10), side="SHORT")  # ratio=2.0

    assert result.is_allowed is False
    assert "spike_detected" in (result.reason or "")
    assert "chasing SHORT" in (result.reason or "")
