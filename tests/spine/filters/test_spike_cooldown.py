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


def test_spike_blocks_impulse_candle() -> None:
    """Candle body > 1.5x ATR should be rejected."""
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(120))  # body=20

    result = f.evaluate(candle=candle, atr=Decimal(10))  # ratio=2.0

    assert result.is_allowed is False
    assert "spike_detected" in (result.reason or "")


def test_spike_allows_normal_candle() -> None:
    """Candle body < 1.5x ATR should pass."""
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(105))  # body=5

    result = f.evaluate(candle=candle, atr=Decimal(10))  # ratio=0.5

    assert result.is_allowed is True
    assert result.reason is None


def test_spike_bypasses_when_atr_none() -> None:
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(120))

    result = f.evaluate(candle=candle, atr=None)

    assert result.is_allowed is True


def test_spike_bypasses_when_atr_zero() -> None:
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(120))

    result = f.evaluate(candle=candle, atr=Decimal(0))

    assert result.is_allowed is True


def test_spike_exact_threshold_passes() -> None:
    """Candle body exactly at threshold (1.5x ATR) should pass (> not >=)."""
    config = FilterConfigSchema()
    f = SpikeCooldownFilter(config)
    candle = _make_candle(Decimal(100), Decimal(115))  # body=15

    result = f.evaluate(candle=candle, atr=Decimal(10))  # ratio=1.5

    assert result.is_allowed is True
