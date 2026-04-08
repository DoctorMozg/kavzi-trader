from decimal import Decimal
from typing import Literal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.schemas.analyst import (
    AnalystDecisionSchema,
    KeyLevelSchema,
    KeyLevelsSchema,
)
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.external.schemas import SentimentSummarySchema


def test_context_builder_analyst(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
) -> None:
    deps = AnalystDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()
    context = builder.build_analyst_context(deps)
    assert context["order_flow_compact"] is not None, "Expected order flow JSON."
    assert "algorithm_confluence_long" in context, "Expected LONG confluence dict."
    assert "algorithm_confluence_short" in context, "Expected SHORT confluence dict."
    assert "detected_side" in context, "Expected detected side."
    assert "market_snapshot" in context, "Expected structured market snapshot dict."
    assert context["futures_leverage"] == 5


def test_context_builder_trader(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
    positions,
) -> None:
    deps = TradingDependenciesSchema(
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
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(deps)
    assert "account_state" in context, "Expected structured account state dict."
    assert context["analyst_result"] is None, "Expected None without analyst result."
    assert context["futures_leverage"] == 5
    assert context["liquidation_distance_percent"] == 20.0
    assert "BTCUSDT" in context["open_positions_json"]
    assert context["funding_rate_24h_percent"] is not None


def test_context_builder_trader_with_analyst_result(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
    positions,
) -> None:
    deps = TradingDependenciesSchema(
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
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )
    analyst_result = AnalystDecisionSchema(
        setup_valid=True,
        direction="LONG",
        confluence_score=8,
        key_levels=KeyLevelsSchema(levels=[]),
        reasoning=(
            "EMA alignment is bullish with EMA20 above EMA50 above EMA200. RSI at 55"
            " supports continuation. Volume confirms the breakout."
        ),
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(deps, analyst_result=analyst_result)
    assert context["analyst_result"] is analyst_result, (
        "Expected analyst_result object in context."
    )
    assert context["analyst_result"].direction == "LONG"


def test_trader_context_no_positions(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
) -> None:
    deps = TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        open_positions=[],
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(deps)
    assert context["open_positions_json"] == "No open positions."


def test_trader_context_funding_cost(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
) -> None:
    deps = TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(deps)
    assert context["funding_rate_24h_percent"] is not None
    assert "%" in context["funding_rate_24h_percent"]


def test_trader_context_no_funding_without_order_flow(
    candle,
    indicators,
    algorithm_confluence,
    volatility_regime,
    account_state,
) -> None:
    deps = TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=None,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(deps)
    assert context["funding_rate_24h_percent"] is None


def test_trader_context_includes_scout_pattern(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
) -> None:
    deps = TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(
        deps,
        scout_pattern="VOLUME_SPIKE",
    )
    assert context["scout_pattern"] == "VOLUME_SPIKE"


def test_trader_context_scout_pattern_defaults_to_none(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
) -> None:
    deps = TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(deps)
    assert context["scout_pattern"] is None


def test_analyst_context_with_sentiment(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
) -> None:
    summary = SentimentSummarySchema(
        summary="Options show elevated IV. Fear index at extreme fear.",
        sentiment_bias="BEARISH",
        confidence_adjustment=Decimal("-0.05"),
    )
    deps = AnalystDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        sentiment_summary=summary,
    )
    builder = ContextBuilder()
    context = builder.build_analyst_context(deps)
    assert context["sentiment_summary"] == summary.summary
    assert context["sentiment_bias"] == "BEARISH"
    assert context["sentiment_confidence_adjustment"] == "-0.05"


def test_analyst_context_without_sentiment(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
) -> None:
    deps = AnalystDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()
    context = builder.build_analyst_context(deps)
    assert context["sentiment_summary"] is None
    assert context["sentiment_bias"] is None
    assert context["sentiment_confidence_adjustment"] is None


def test_trader_context_with_sentiment(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
) -> None:
    summary = SentimentSummarySchema(
        summary="Market neutral with moderate volatility.",
        sentiment_bias="NEUTRAL",
        confidence_adjustment=Decimal("0.00"),
    )
    deps = TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        open_positions=[],
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
        sentiment_summary=summary,
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(deps)
    assert context["sentiment_summary"] == summary.summary
    assert context["sentiment_bias"] == "NEUTRAL"


# --- ATR fallback target tests ---


def _make_analyst(
    direction: Literal["LONG", "SHORT", "NEUTRAL"],
    levels: list[KeyLevelSchema] | None = None,
) -> AnalystDecisionSchema:
    return AnalystDecisionSchema(
        setup_valid=True,
        direction=direction,
        confluence_score=8,
        key_levels=KeyLevelsSchema(levels=levels or []),
        reasoning=(
            "EMA alignment is bullish with EMA20 above EMA50 above EMA200. RSI at 55"
            " supports continuation. Volume confirms the breakout."
        ),
    )


def test_atr_fallback_long_no_resistance_above() -> None:
    """LONG with all RESISTANCE below current_price -> ATR targets generated."""
    builder = ContextBuilder()
    analyst = _make_analyst(
        "LONG",
        [
            KeyLevelSchema(
                price=Decimal(100), level_type="RESISTANCE", reason="swing high"
            )
        ],
    )
    targets = builder._compute_atr_fallback_targets(
        analyst_result=analyst,
        current_price=Decimal(105),
        atr=Decimal(2),
    )
    assert len(targets) == 2
    assert Decimal(targets[0]["price"]) == Decimal(109)  # 105 + 2.0*2
    assert Decimal(targets[1]["price"]) == Decimal(111)  # 105 + 3.0*2


def test_atr_fallback_long_has_resistance_above() -> None:
    """LONG with RESISTANCE above current_price -> ATR targets still generated."""
    builder = ContextBuilder()
    analyst = _make_analyst(
        "LONG",
        [
            KeyLevelSchema(
                price=Decimal(110), level_type="RESISTANCE", reason="swing high"
            )
        ],
    )
    targets = builder._compute_atr_fallback_targets(
        analyst_result=analyst,
        current_price=Decimal(105),
        atr=Decimal(2),
    )
    assert len(targets) == 2
    assert Decimal(targets[0]["price"]) == Decimal(109)  # 105 + 2.0*2
    assert Decimal(targets[1]["price"]) == Decimal(111)  # 105 + 3.0*2


def test_atr_fallback_short_no_support_below() -> None:
    """SHORT with no SUPPORT below current_price -> ATR targets generated."""
    builder = ContextBuilder()
    analyst = _make_analyst(
        "SHORT",
        [KeyLevelSchema(price=Decimal(110), level_type="SUPPORT", reason="old low")],
    )
    targets = builder._compute_atr_fallback_targets(
        analyst_result=analyst,
        current_price=Decimal(105),
        atr=Decimal(2),
    )
    assert len(targets) == 2
    assert Decimal(targets[0]["price"]) == Decimal(101)  # 105 - 2.0*2
    assert Decimal(targets[1]["price"]) == Decimal(99)  # 105 - 3.0*2


def test_atr_fallback_short_has_support_below() -> None:
    """SHORT with SUPPORT below current_price -> ATR targets still generated."""
    builder = ContextBuilder()
    analyst = _make_analyst(
        "SHORT",
        [KeyLevelSchema(price=Decimal(100), level_type="SUPPORT", reason="swing low")],
    )
    targets = builder._compute_atr_fallback_targets(
        analyst_result=analyst,
        current_price=Decimal(105),
        atr=Decimal(2),
    )
    assert len(targets) == 2
    assert Decimal(targets[0]["price"]) == Decimal(101)  # 105 - 2.0*2
    assert Decimal(targets[1]["price"]) == Decimal(99)  # 105 - 3.0*2


def test_atr_fallback_neutral_returns_empty() -> None:
    """NEUTRAL direction -> no fallback targets."""
    builder = ContextBuilder()
    analyst = _make_analyst("NEUTRAL")
    targets = builder._compute_atr_fallback_targets(
        analyst_result=analyst,
        current_price=Decimal(105),
        atr=Decimal(2),
    )
    assert targets == []


def test_atr_fallback_none_analyst_returns_empty() -> None:
    """No analyst result -> no fallback targets."""
    builder = ContextBuilder()
    targets = builder._compute_atr_fallback_targets(
        analyst_result=None,
        current_price=Decimal(105),
        atr=Decimal(2),
    )
    assert targets == []


def test_atr_fallback_none_atr_returns_empty() -> None:
    """ATR is None -> no fallback targets."""
    builder = ContextBuilder()
    analyst = _make_analyst("LONG")
    targets = builder._compute_atr_fallback_targets(
        analyst_result=analyst,
        current_price=Decimal(105),
        atr=None,
    )
    assert targets == []


def test_atr_fallback_zero_atr_returns_empty() -> None:
    """ATR is zero -> no fallback targets."""
    builder = ContextBuilder()
    analyst = _make_analyst("LONG")
    targets = builder._compute_atr_fallback_targets(
        analyst_result=analyst,
        current_price=Decimal(105),
        atr=Decimal(0),
    )
    assert targets == []


def test_atr_fallback_injected_in_trader_context(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
) -> None:
    """Full integration: fallback targets appear in trader context when needed."""
    deps = TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        open_positions=[],
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )
    # Analyst with LONG direction but all resistance levels below current_price
    analyst = _make_analyst(
        "LONG",
        [
            KeyLevelSchema(
                price=Decimal(100), level_type="RESISTANCE", reason="old high"
            )
        ],
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(deps, analyst_result=analyst)
    fallback = context["atr_fallback_targets"]
    assert len(fallback) == 2
    assert "ATR projection" in fallback[0]["label"]


def test_atr_fallback_always_provided_alongside_structural() -> None:
    """LONG with valid RESISTANCE above current price still returns ATR projections."""
    builder = ContextBuilder()
    analyst = _make_analyst(
        "LONG",
        [
            KeyLevelSchema(
                price=Decimal(108),
                level_type="RESISTANCE",
                reason="structural high",
            ),
            KeyLevelSchema(
                price=Decimal(112),
                level_type="RESISTANCE",
                reason="swing high",
            ),
        ],
    )
    targets = builder._compute_atr_fallback_targets(
        analyst_result=analyst,
        current_price=Decimal(105),
        atr=Decimal(2),
    )
    assert len(targets) == 2
    assert Decimal(targets[0]["price"]) == Decimal(109)  # 105 + 2.0*2
    assert Decimal(targets[1]["price"]) == Decimal(111)  # 105 + 3.0*2
    assert targets[0]["label"] == "ATR projection 2.0x"
    assert targets[1]["label"] == "ATR projection 3.0x"
