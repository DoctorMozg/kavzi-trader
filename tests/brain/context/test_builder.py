import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.schemas.analyst import (
    AnalystDecisionSchema,
    KeyLevelsSchema,
)
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema


def test_context_builder_scout(candle, indicators, volatility_regime) -> None:
    deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()
    context = builder.build_scout_context(deps)
    assert "market_snapshot" in context, "Expected structured market snapshot dict."
    assert "market_snapshot_json" not in context, "Scout should not include full JSON."
    assert context["market_snapshot"]["symbol"] == "BTCUSDT"


def test_context_builder_scout_logs_recent_candle_count(
    caplog,
    candle,
    indicators,
    volatility_regime,
) -> None:
    deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()

    with caplog.at_level(logging.DEBUG):
        builder.build_scout_context(deps)

    assert "Built scout context for BTCUSDT: context_keys=" in caplog.text


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


def _make_candle(close_price: Decimal) -> CandlestickSchema:
    now = utc_now()
    return CandlestickSchema(
        open_time=now,
        open_price=Decimal(100),
        high_price=close_price + 1,
        low_price=close_price - 1,
        close_price=close_price,
        volume=Decimal(1000),
        close_time=now,
        quote_volume=Decimal(100000),
        trades_count=100,
        taker_buy_base_volume=Decimal(600),
        taker_buy_quote_volume=Decimal(60000),
        interval="1m",
        symbol="BTCUSDT",
    )


def test_scout_context_includes_trend_context(
    indicators,
    volatility_regime,
) -> None:
    candles = [_make_candle(Decimal(100)), _make_candle(Decimal(105))]
    deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="1m",
        recent_candles=candles,
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()
    context = builder.build_scout_context(deps)
    assert "price_change_window_percent" in context
    assert context["price_change_window_percent"] == 5.0
    assert context["candle_window_size"] == 2
    assert "ema_alignment" in context


def test_scout_context_bullish_alignment(volatility_regime) -> None:
    candles = [_make_candle(Decimal(100)), _make_candle(Decimal(105))]
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(110),
        ema_50=Decimal(105),
        ema_200=Decimal(90),
        sma_20=Decimal(100),
        rsi_14=Decimal(50),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=None,
        timestamp=utc_now(),
    )
    deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(112),
        timeframe="1m",
        recent_candles=candles,
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()
    context = builder.build_scout_context(deps)
    assert context["ema_alignment"] == "BULLISH"


def test_scout_context_neutral_alignment(volatility_regime) -> None:
    candles = [_make_candle(Decimal(100)), _make_candle(Decimal(102))]
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(110),
        ema_50=Decimal(90),
        ema_200=Decimal(105),
        sma_20=Decimal(100),
        rsi_14=Decimal(50),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=None,
        timestamp=utc_now(),
    )
    deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(102),
        timeframe="1m",
        recent_candles=candles,
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()
    context = builder.build_scout_context(deps)
    assert context["ema_alignment"] == "NEUTRAL"
