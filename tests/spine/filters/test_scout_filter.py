from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.schemas.dependencies import ScoutDependenciesSchema
from kavzi_trader.indicators.schemas import (
    BollingerBandsSchema,
    MACDResultSchema,
    TechnicalIndicatorsSchema,
    VolumeAnalysisSchema,
)
from kavzi_trader.spine.filters.scout import ScoutFilter
from kavzi_trader.spine.filters.scout_config import ScoutConfigSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _make_candle(
    close: Decimal,
    open_: Decimal = Decimal(100),
    high: Decimal | None = None,
    low: Decimal | None = None,
    offset_min: int = 0,
) -> CandlestickSchema:
    t = _NOW + timedelta(minutes=offset_min)
    return CandlestickSchema(
        open_time=t,
        open_price=open_,
        high_price=high or max(open_, close) + 1,
        low_price=low or min(open_, close) - 1,
        close_price=close,
        volume=Decimal(1000),
        close_time=t + timedelta(minutes=5),
        quote_volume=Decimal(100000),
        trades_count=100,
        taker_buy_base_volume=Decimal(500),
        taker_buy_quote_volume=Decimal(50000),
        interval="5m",
        symbol="BTCUSDT",
    )


def _make_indicators(
    *,
    ema_20: Decimal | None = Decimal(100),
    ema_50: Decimal | None = Decimal(98),
    ema_200: Decimal | None = Decimal(90),
    rsi_14: Decimal | None = Decimal(50),
    vol_ratio: Decimal | None = Decimal("1.0"),
    percent_b: Decimal | None = Decimal("0.5"),
    macd_histogram: Decimal | None = None,
) -> TechnicalIndicatorsSchema:
    volume = (
        VolumeAnalysisSchema(
            current_volume=Decimal(1000),
            average_volume=Decimal(1000),
            volume_ratio=vol_ratio,
            obv=None,
        )
        if vol_ratio is not None
        else None
    )
    bollinger = (
        BollingerBandsSchema(
            upper=Decimal(110),
            middle=Decimal(100),
            lower=Decimal(90),
            width=Decimal("0.2"),
            percent_b=percent_b,
        )
        if percent_b is not None
        else None
    )
    macd = (
        MACDResultSchema(
            macd_line=macd_histogram or Decimal(0),
            signal_line=Decimal(0),
            histogram=macd_histogram,
        )
        if macd_histogram is not None
        else None
    )
    return TechnicalIndicatorsSchema(
        ema_20=ema_20,
        ema_50=ema_50,
        ema_200=ema_200,
        sma_20=Decimal(100),
        rsi_14=rsi_14,
        macd=macd,
        bollinger=bollinger,
        atr_14=Decimal(5),
        volume=volume,
        timestamp=_NOW,
    )


def _make_deps(
    indicators: TechnicalIndicatorsSchema,
    regime: VolatilityRegime = VolatilityRegime.NORMAL,
    candles: list[CandlestickSchema] | None = None,
) -> ScoutDependenciesSchema:
    return ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="5m",
        recent_candles=candles or [_make_candle(Decimal(105))],
        indicators=indicators,
        volatility_regime=regime,
    )


@pytest.fixture
def cfg() -> ScoutConfigSchema:
    return ScoutConfigSchema()


@pytest.fixture
def scout(cfg: ScoutConfigSchema) -> ScoutFilter:
    return ScoutFilter(cfg)


# ------------------------------------------------------------------
# Volatility gate
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_low_regime_skip(scout: ScoutFilter) -> None:
    deps = _make_deps(_make_indicators(), regime=VolatilityRegime.LOW)
    result = await scout.run(deps)
    assert result.verdict == "SKIP"
    assert "Volatility regime LOW" in result.reason


@pytest.mark.asyncio
async def test_extreme_regime_skip(scout: ScoutFilter) -> None:
    deps = _make_deps(_make_indicators(), regime=VolatilityRegime.EXTREME)
    result = await scout.run(deps)
    assert result.verdict == "SKIP"
    assert "Volatility regime EXTREME" in result.reason


@pytest.mark.asyncio
async def test_normal_regime_proceeds(scout: ScoutFilter) -> None:
    deps = _make_deps(_make_indicators(), regime=VolatilityRegime.NORMAL)
    result = await scout.run(deps)
    assert "Volatility regime" not in result.reason


@pytest.mark.asyncio
async def test_high_regime_proceeds(scout: ScoutFilter) -> None:
    deps = _make_deps(_make_indicators(), regime=VolatilityRegime.HIGH)
    result = await scout.run(deps)
    assert "Volatility regime" not in result.reason


# ------------------------------------------------------------------
# Volume gates
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_volume_skip(scout: ScoutFilter) -> None:
    ind = _make_indicators(vol_ratio=Decimal("0.2"))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.verdict == "SKIP"
    assert "Volume too low" in result.reason


@pytest.mark.asyncio
async def test_soft_volume_skip_no_pattern(scout: ScoutFilter) -> None:
    """Low volume with no matching criterion → SKIP."""
    ind = _make_indicators(vol_ratio=Decimal("0.5"), rsi_14=Decimal(50))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.verdict == "SKIP"
    assert "Low volume" in result.reason or "No pattern" in result.reason


# ------------------------------------------------------------------
# Criterion 1: BREAKOUT
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breakout_upper(scout: ScoutFilter) -> None:
    ind = _make_indicators(percent_b=Decimal("1.05"), vol_ratio=Decimal("1.5"))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert "BREAKOUT" in result.reason
    assert result.pattern_detected == "BREAKOUT"


@pytest.mark.asyncio
async def test_breakout_lower(scout: ScoutFilter) -> None:
    ind = _make_indicators(percent_b=Decimal("-0.05"), vol_ratio=Decimal("1.3"))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert result.pattern_detected == "BREAKOUT"


@pytest.mark.asyncio
async def test_breakout_insufficient_volume(scout: ScoutFilter) -> None:
    ind = _make_indicators(percent_b=Decimal("1.1"), vol_ratio=Decimal("1.0"))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    # vol_ratio=1.0 < breakout_vol_ratio_min=1.2, so breakout fails
    assert result.pattern_detected != "BREAKOUT"


# ------------------------------------------------------------------
# Criterion 2: TREND CONTINUATION
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trend_continuation_bullish(scout: ScoutFilter) -> None:
    ind = _make_indicators(
        ema_20=Decimal(110),
        ema_50=Decimal(105),
        ema_200=Decimal(90),
        rsi_14=Decimal(55),
        vol_ratio=Decimal("1.2"),
    )
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert "TREND_CONTINUATION" in result.reason
    assert "BULLISH" in result.reason


@pytest.mark.asyncio
async def test_trend_continuation_bearish(scout: ScoutFilter) -> None:
    ind = _make_indicators(
        ema_20=Decimal(85),
        ema_50=Decimal(90),
        ema_200=Decimal(100),
        rsi_14=Decimal(45),
        vol_ratio=Decimal("1.1"),
    )
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert "BEARISH" in result.reason


@pytest.mark.asyncio
async def test_trend_continuation_neutral_alignment(scout: ScoutFilter) -> None:
    """Neutral EMA alignment → no trend continuation."""
    ind = _make_indicators(
        ema_20=Decimal(100),
        ema_50=Decimal(90),
        ema_200=Decimal(95),
        rsi_14=Decimal(50),
        vol_ratio=Decimal("1.5"),
    )
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.pattern_detected != "TREND_CONTINUATION"


# ------------------------------------------------------------------
# Criterion 3: REVERSAL
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reversal_oversold(scout: ScoutFilter) -> None:
    ind = _make_indicators(rsi_14=Decimal(25), percent_b=Decimal("0.05"))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert result.pattern_detected == "REVERSAL"


@pytest.mark.asyncio
async def test_reversal_overbought(scout: ScoutFilter) -> None:
    ind = _make_indicators(rsi_14=Decimal(75), percent_b=Decimal("0.95"))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert result.pattern_detected == "REVERSAL"


@pytest.mark.asyncio
async def test_reversal_rsi_extreme_without_bb(scout: ScoutFilter) -> None:
    """RSI extreme but %B in mid-range → no reversal."""
    ind = _make_indicators(rsi_14=Decimal(25), percent_b=Decimal("0.5"))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.pattern_detected != "REVERSAL"


# ------------------------------------------------------------------
# Criterion 4: VOLUME SPIKE
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_volume_spike_with_ema_support(scout: ScoutFilter) -> None:
    ind = _make_indicators(
        ema_20=Decimal(110),
        ema_50=Decimal(105),
        ema_200=Decimal(90),
        vol_ratio=Decimal("2.5"),
        rsi_14=Decimal(65),  # outside trend range (40-60) so criterion 2 skips
    )
    candle = _make_candle(
        close=Decimal(108),
        open_=Decimal(100),
        high=Decimal(110),
        low=Decimal(99),
    )
    deps = _make_deps(ind, candles=[candle])
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert result.pattern_detected == "VOLUME_SPIKE"


@pytest.mark.asyncio
async def test_volume_spike_without_support_skip(scout: ScoutFilter) -> None:
    """Volume spike but no supporting signal → SKIP."""
    ind = _make_indicators(
        ema_20=Decimal(100),
        ema_50=Decimal(90),
        ema_200=Decimal(95),  # NEUTRAL
        rsi_14=Decimal(50),  # not extreme
        percent_b=Decimal("0.5"),  # mid-range
        vol_ratio=Decimal("2.5"),
    )
    candle = _make_candle(
        close=Decimal(108),
        open_=Decimal(100),
        high=Decimal(110),
        low=Decimal(99),
    )
    deps = _make_deps(ind, candles=[candle])
    result = await scout.run(deps)
    assert result.pattern_detected != "VOLUME_SPIKE"


@pytest.mark.asyncio
async def test_volume_spike_small_body_skip(scout: ScoutFilter) -> None:
    """Spike volume but doji candle → SKIP."""
    ind = _make_indicators(
        ema_20=Decimal(110),
        ema_50=Decimal(105),
        ema_200=Decimal(90),
        vol_ratio=Decimal("3.0"),
    )
    candle = _make_candle(
        close=Decimal("100.1"),
        open_=Decimal(100),
        high=Decimal(110),
        low=Decimal(90),
    )
    deps = _make_deps(ind, candles=[candle])
    result = await scout.run(deps)
    assert result.pattern_detected != "VOLUME_SPIKE"


# ------------------------------------------------------------------
# Criterion 5: MOMENTUM SHIFT
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_momentum_shift(scout: ScoutFilter) -> None:
    """Bullish MACD histogram with 2 bearish preceding candles (default N=3)."""
    ind = _make_indicators(
        macd_histogram=Decimal("0.5"),
        ema_20=Decimal(100),
        ema_50=Decimal(90),
        ema_200=Decimal(95),  # NEUTRAL alignment → criterion 2 skips
    )
    candles = [
        _make_candle(Decimal(97), open_=Decimal(100), offset_min=0),  # bearish
        _make_candle(Decimal(95), open_=Decimal(98), offset_min=5),  # bearish
        _make_candle(Decimal(105), open_=Decimal(100), offset_min=10),  # bullish
    ]
    deps = _make_deps(ind, candles=candles)
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert result.pattern_detected == "MOMENTUM_SHIFT"


@pytest.mark.asyncio
async def test_momentum_shift_mixed_preceding_skip(scout: ScoutFilter) -> None:
    """One bearish + one bullish preceding candle → no consistent opposition."""
    ind = _make_indicators(
        macd_histogram=Decimal("0.5"),
        ema_20=Decimal(100),
        ema_50=Decimal(90),
        ema_200=Decimal(95),
    )
    candles = [
        _make_candle(Decimal(95), open_=Decimal(100), offset_min=0),  # bearish
        _make_candle(Decimal(103), open_=Decimal(100), offset_min=5),  # bullish!
        _make_candle(Decimal(108), open_=Decimal(103), offset_min=10),  # bullish
    ]
    deps = _make_deps(ind, candles=candles)
    result = await scout.run(deps)
    assert result.pattern_detected != "MOMENTUM_SHIFT"


@pytest.mark.asyncio
async def test_momentum_shift_no_change(scout: ScoutFilter) -> None:
    """Bullish MACD with bullish previous candles → no shift."""
    ind = _make_indicators(macd_histogram=Decimal("0.5"))
    candles = [
        _make_candle(Decimal(102), open_=Decimal(100), offset_min=0),  # bullish
        _make_candle(Decimal(105), open_=Decimal(100), offset_min=5),  # bullish
        _make_candle(Decimal(108), open_=Decimal(103), offset_min=10),  # bullish
    ]
    deps = _make_deps(ind, candles=candles)
    result = await scout.run(deps)
    assert result.pattern_detected != "MOMENTUM_SHIFT"


@pytest.mark.asyncio
async def test_momentum_shift_insufficient_candles(scout: ScoutFilter) -> None:
    """Only two candles with default N=3 → cannot detect momentum shift."""
    ind = _make_indicators(macd_histogram=Decimal("0.5"))
    candles = [
        _make_candle(Decimal(95), open_=Decimal(100), offset_min=0),
        _make_candle(Decimal(105), open_=Decimal(100), offset_min=5),
    ]
    deps = _make_deps(ind, candles=candles)
    result = await scout.run(deps)
    assert result.pattern_detected != "MOMENTUM_SHIFT"


# ------------------------------------------------------------------
# Criterion 6: TREND WITH PULLBACK
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trend_pullback_bullish(scout: ScoutFilter) -> None:
    ind = _make_indicators(
        ema_20=Decimal(110),
        ema_50=Decimal(105),
        ema_200=Decimal(90),
        rsi_14=Decimal(65),  # outside trend range → criterion 2 skips
        vol_ratio=Decimal("0.9"),  # below trend_vol_ratio_min → criterion 2 skips
    )
    candles = [
        _make_candle(Decimal(100), offset_min=0),
        _make_candle(Decimal(102), offset_min=5),
    ]
    deps = _make_deps(ind, candles=candles)
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert result.pattern_detected == "TREND_PULLBACK"
    assert "BULLISH" in result.reason


@pytest.mark.asyncio
async def test_trend_pullback_bearish(scout: ScoutFilter) -> None:
    ind = _make_indicators(
        ema_20=Decimal(85),
        ema_50=Decimal(90),
        ema_200=Decimal(100),
        rsi_14=Decimal(35),  # outside trend range → criterion 2 skips
        vol_ratio=Decimal("0.9"),  # below trend_vol_ratio_min → criterion 2 skips
    )
    candles = [
        _make_candle(Decimal(100), offset_min=0),
        _make_candle(Decimal(98), offset_min=5),
    ]
    deps = _make_deps(ind, candles=candles)
    result = await scout.run(deps)
    assert result.verdict == "INTERESTING"
    assert result.pattern_detected == "TREND_PULLBACK"
    assert "BEARISH" in result.reason


@pytest.mark.asyncio
async def test_trend_pullback_too_small(scout: ScoutFilter) -> None:
    """Price change < 1.5% → no pullback criterion."""
    ind = _make_indicators(
        ema_20=Decimal(110),
        ema_50=Decimal(105),
        ema_200=Decimal(90),
    )
    candles = [
        _make_candle(Decimal(100), offset_min=0),
        _make_candle(Decimal("100.3"), offset_min=5),
    ]
    deps = _make_deps(ind, candles=candles)
    result = await scout.run(deps)
    assert result.pattern_detected != "TREND_PULLBACK"


# ------------------------------------------------------------------
# No criteria met
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_pattern_detected(scout: ScoutFilter) -> None:
    """Flat market, no signals → SKIP."""
    ind = _make_indicators(
        ema_20=Decimal(100),
        ema_50=Decimal(90),
        ema_200=Decimal(95),
        rsi_14=Decimal(50),
        vol_ratio=Decimal("1.0"),
        percent_b=Decimal("0.5"),
    )
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.verdict == "SKIP"
    assert result.pattern_detected is None


# ------------------------------------------------------------------
# Null indicator handling
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_null_bollinger_skips_breakout_reversal(scout: ScoutFilter) -> None:
    ind = _make_indicators(percent_b=None, vol_ratio=Decimal("2.0"))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.pattern_detected not in ("BREAKOUT", "REVERSAL")


@pytest.mark.asyncio
async def test_null_volume(scout: ScoutFilter) -> None:
    ind = _make_indicators(vol_ratio=None)
    deps = _make_deps(ind)
    result = await scout.run(deps)
    # Should not crash, just skip volume-dependent criteria
    assert result.verdict == "SKIP"


# ------------------------------------------------------------------
# Config overrides
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_blocked_regimes() -> None:
    """Only EXTREME blocked; LOW regime should proceed."""
    cfg = ScoutConfigSchema(blocked_regimes=["EXTREME"])
    scout = ScoutFilter(cfg)
    ind = _make_indicators(
        ema_20=Decimal(110),
        ema_50=Decimal(105),
        ema_200=Decimal(90),
        rsi_14=Decimal(55),
        vol_ratio=Decimal("1.5"),
    )
    deps = _make_deps(ind, regime=VolatilityRegime.LOW)
    result = await scout.run(deps)
    # LOW is NOT blocked, so criteria are evaluated
    assert "Volatility regime" not in result.reason


@pytest.mark.asyncio
async def test_custom_breakout_threshold() -> None:
    """Stricter breakout volume threshold blocks a marginal breakout."""
    cfg = ScoutConfigSchema(breakout_vol_ratio_min=Decimal("2.0"))
    scout = ScoutFilter(cfg)
    ind = _make_indicators(percent_b=Decimal("1.1"), vol_ratio=Decimal("1.5"))
    deps = _make_deps(ind)
    result = await scout.run(deps)
    assert result.pattern_detected != "BREAKOUT"
