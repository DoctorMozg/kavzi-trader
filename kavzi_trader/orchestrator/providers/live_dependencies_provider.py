import logging
from decimal import Decimal
from typing import Literal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)

RECENT_CANDLES_COUNT = 50


class LiveDependenciesProvider:
    """Builds live dependency schemas from the shared market data cache."""

    def __init__(
        self,
        cache: MarketDataCache,
        confluence_calculator: ConfluenceCalculator,
        volatility_detector: VolatilityRegimeDetector,
        state_manager: StateManager,
        exchange: BinanceClient,
        event_store: RedisEventStore,
        timeframe: str,
    ) -> None:
        self._cache = cache
        self._confluence = confluence_calculator
        self._volatility = volatility_detector
        self._state_manager = state_manager
        self._exchange = exchange
        self._event_store = event_store
        self._timeframe = timeframe

    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema:
        candles = self._cache.get_candles(symbol)
        indicators = self._cache.get_indicators(symbol)
        if indicators is None:
            msg = "Indicators not yet available for %s" % symbol
            raise RuntimeError(msg)

        price = self._cache.get_current_price(symbol)
        atr_history = self._cache.get_atr_history(symbol)
        current_atr = indicators.atr_14 or Decimal("0")
        regime_result = self._volatility.detect_regime(
            current_atr, atr_history,
        )

        recent = candles[-RECENT_CANDLES_COUNT:]
        return ScoutDependenciesSchema(
            symbol=symbol,
            current_price=price,
            timeframe=self._timeframe,
            recent_candles=recent,
            indicators=indicators,
            volatility_regime=regime_result.regime,
        )

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema:
        candles = self._cache.get_candles(symbol)
        indicators = self._cache.get_indicators(symbol)
        if indicators is None:
            msg = "Indicators not yet available for %s" % symbol
            raise RuntimeError(msg)

        price = self._cache.get_current_price(symbol)
        atr_history = self._cache.get_atr_history(symbol)
        current_atr = indicators.atr_14 or Decimal("0")
        regime_result = self._volatility.detect_regime(
            current_atr, atr_history,
        )

        order_flow = self._cache.get_order_flow(symbol)

        side: Literal["LONG", "SHORT"] = "LONG"
        if indicators.ema_20 is not None and indicators.ema_50 is not None:
            side = (
                "LONG" if indicators.ema_20 > indicators.ema_50 else "SHORT"
            )

        last_candle = candles[-1] if candles else None
        if last_candle is None:
            msg = "No candles available for %s" % symbol
            raise RuntimeError(msg)

        confluence = self._confluence.evaluate(
            side, last_candle, indicators, order_flow,
        )

        recent = candles[-RECENT_CANDLES_COUNT:]
        return AnalystDependenciesSchema(
            symbol=symbol,
            current_price=price,
            timeframe=self._timeframe,
            recent_candles=recent,
            indicators=indicators,
            order_flow=order_flow,
            algorithm_confluence=confluence,
            volatility_regime=regime_result.regime,
        )

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema:
        candles = self._cache.get_candles(symbol)
        indicators = self._cache.get_indicators(symbol)
        if indicators is None:
            msg = "Indicators not yet available for %s" % symbol
            raise RuntimeError(msg)

        price = self._cache.get_current_price(symbol)
        atr_history = self._cache.get_atr_history(symbol)
        current_atr = indicators.atr_14 or Decimal("0")
        regime_result = self._volatility.detect_regime(
            current_atr, atr_history,
        )

        order_flow = self._cache.get_order_flow(symbol)

        side: Literal["LONG", "SHORT"] = "LONG"
        if indicators.ema_20 is not None and indicators.ema_50 is not None:
            side = (
                "LONG" if indicators.ema_20 > indicators.ema_50 else "SHORT"
            )

        last_candle = candles[-1] if candles else None
        if last_candle is None:
            msg = "No candles available for %s" % symbol
            raise RuntimeError(msg)

        confluence = self._confluence.evaluate(
            side, last_candle, indicators, order_flow,
        )

        account_state = await self._state_manager.get_account_state()
        if account_state is None:
            msg = "Account state not available"
            raise RuntimeError(msg)

        open_positions = await self._state_manager.get_all_positions()

        recent = candles[-RECENT_CANDLES_COUNT:]
        return TradingDependenciesSchema(
            symbol=symbol,
            current_price=price,
            timeframe=self._timeframe,
            recent_candles=recent,
            indicators=indicators,
            order_flow=order_flow,
            algorithm_confluence=confluence,
            volatility_regime=regime_result.regime,
            account_state=account_state,
            open_positions=open_positions,
            exchange_client=self._exchange,
            event_store=self._event_store,
        )
