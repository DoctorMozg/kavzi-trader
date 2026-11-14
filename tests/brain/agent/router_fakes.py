from datetime import timedelta
from decimal import Decimal

from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.domain.analyst_decision import (
    AnalystDecisionSchema,
    KeyLevelsSchema,
)
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.indicator_schemas import (
    BollingerBandsSchema,
    TechnicalIndicatorsSchema,
)
from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.scout_dependencies import ScoutDependenciesSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema

# NOTE: VolatilityRegime is still imported for fixture construction but the
# volatility gate itself now lives inside ScoutFilter, not in the router.

_ANALYST_REASONING = (
    "EMA alignment is bullish with EMA20 above EMA50 above EMA200. RSI at 55 supports"
    " continuation. Volume confirms the breakout. Volatility regime is NORMAL."
)


_TRADER_REASONING = (
    "Mixed signals across all timeframes. EMA alignment is neutral and RSI is flat"
    " at 50. No clear directional bias to justify a trade entry at this time."
)


class DummyScout:
    def __init__(self, verdict: str) -> None:
        self._verdict = verdict

    async def run(self, deps):
        return ScoutDecisionSchema(
            verdict=self._verdict,
            reason="Test",
            pattern_detected=None,
        )


class DummyAnalyst:
    def __init__(self, setup_valid: bool, confluence_score: int = 5) -> None:
        self._setup_valid = setup_valid
        self._confluence_score = confluence_score
        self.call_count = 0

    async def run(self, deps):
        self.call_count += 1
        return AnalystDecisionSchema(
            setup_valid=self._setup_valid,
            direction="NEUTRAL",
            confluence_score=self._confluence_score,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_ANALYST_REASONING,
        )


class DummyTrader:
    async def run(self, deps, analyst_result=None, scout_pattern=None):
        return TradeDecisionSchema(
            action="WAIT",
            confidence=0.5,
            reasoning=_TRADER_REASONING,
        )


class FakeDepsProvider:
    def __init__(
        self,
        scout_deps: ScoutDependenciesSchema,
        analyst_deps: AnalystDependenciesSchema,
        trader_deps: TradingDependenciesSchema,
    ) -> None:
        self._scout_deps = scout_deps
        self._analyst_deps = analyst_deps
        self._trader_deps = trader_deps
        self.scout_calls = 0
        self.analyst_calls = 0
        self.trader_calls = 0

    def indicators_available(self, symbol: str) -> bool:
        return True

    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema:
        self.scout_calls += 1
        return self._scout_deps

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema:
        self.analyst_calls += 1
        return self._analyst_deps

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema:
        self.trader_calls += 1
        return self._trader_deps

    def clear_cycle_cache(self) -> None:
        pass


def _make_provider(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> FakeDepsProvider:
    scout_deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    analyst_deps = AnalystDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
    )
    trader_deps = TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        open_positions=positions,
    )
    return FakeDepsProvider(scout_deps, analyst_deps, trader_deps)


class SpyScout:
    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        self.call_count += 1
        return ScoutDecisionSchema(
            verdict="INTERESTING",
            reason="Test",
            pattern_detected=None,
        )


# ---------------------------------------------------------------------------
# Bar-close dedup: the router must memoize the Analyst result per
# (symbol, candle.close_time). Repeat calls within the same bar return the
# cached result without invoking the LLM a second time.
# ---------------------------------------------------------------------------


def _candle_with_close_time(
    base: CandlestickSchema, offset_s: int
) -> CandlestickSchema:
    return CandlestickSchema(
        open_time=base.open_time + timedelta(seconds=offset_s),
        close_time=base.close_time + timedelta(seconds=offset_s),
        open_price=base.open_price,
        high_price=base.high_price,
        low_price=base.low_price,
        close_price=base.close_price,
        volume=base.volume,
        quote_volume=base.quote_volume,
        trades_count=base.trades_count,
        taker_buy_base_volume=base.taker_buy_base_volume,
        taker_buy_quote_volume=base.taker_buy_quote_volume,
        interval=base.interval,
        symbol=base.symbol,
    )


def _rebuild_provider_with_candle(
    provider: FakeDepsProvider,
    new_candle: CandlestickSchema,
) -> None:
    """Swap in deps whose recent_candles[-1] is the new candle."""
    provider._scout_deps = provider._scout_deps.model_copy(
        update={"recent_candles": [new_candle]},
    )
    provider._analyst_deps = provider._analyst_deps.model_copy(
        update={"recent_candles": [new_candle]},
    )
    provider._trader_deps = provider._trader_deps.model_copy(
        update={"recent_candles": [new_candle]},
    )


# ---------------------------------------------------------------------------
# Breakout overextension gate
# ---------------------------------------------------------------------------


def _indicators_with_bollinger(
    indicators: TechnicalIndicatorsSchema,
    percent_b: Decimal,
) -> TechnicalIndicatorsSchema:
    """Return indicators with a Bollinger Bands schema injected."""
    return TechnicalIndicatorsSchema(
        ema_20=indicators.ema_20,
        ema_50=indicators.ema_50,
        ema_200=indicators.ema_200,
        sma_20=indicators.sma_20,
        rsi_14=indicators.rsi_14,
        macd=indicators.macd,
        bollinger=BollingerBandsSchema(
            upper=Decimal(110),
            middle=Decimal(100),
            lower=Decimal(90),
            width=Decimal("0.2"),
            percent_b=percent_b,
        ),
        atr_14=indicators.atr_14,
        volume=indicators.volume,
        timestamp=indicators.timestamp,
    )


class DummyScoutWithPattern:
    """Scout that returns INTERESTING with a specific pattern."""

    def __init__(self, pattern: str) -> None:
        self._pattern = pattern

    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        return ScoutDecisionSchema(
            verdict="INTERESTING",
            reason="Test",
            pattern_detected=self._pattern,
        )


class SpyTrader:
    """Trader that records whether it was called."""

    def __init__(self) -> None:
        self.call_count = 0

    async def run(
        self,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema | None = None,
        scout_pattern: str | None = None,
    ) -> TradeDecisionSchema:
        self.call_count += 1
        return TradeDecisionSchema(
            action="WAIT",
            confidence=0.5,
            reasoning=_TRADER_REASONING,
        )


class CountedUnexpectedModelTrader:
    """Raises UnexpectedModelBehavior with configurable bodies per call."""

    def __init__(self, bodies: list[str | None]) -> None:
        self._bodies = bodies
        self.call_count = 0

    async def run(self, deps, analyst_result=None, scout_pattern=None):
        from pydantic_ai.exceptions import UnexpectedModelBehavior

        body = self._bodies[self.call_count]
        self.call_count += 1
        raise UnexpectedModelBehavior("Bad output", body=body)
