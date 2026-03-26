import logging
from decimal import Decimal
from typing import Any, Literal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.schemas import AccountStateSchema, PositionSchema

logger = logging.getLogger(__name__)

SCOUT_CANDLES_COUNT = 50
ANALYSIS_CANDLES_COUNT = 20


class LiveDependenciesProvider:
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
        self._cycle_cache: dict[str, Any] = {}

    def clear_cycle_cache(self) -> None:
        self._cycle_cache.clear()

    def _recent_candles(
        self,
        symbol: str,
        count: int = SCOUT_CANDLES_COUNT,
    ) -> list[CandlestickSchema]:
        candles = self._cache.get_candles(symbol)
        return candles[-count:]

    def _detect_side(self, symbol: str) -> Literal["LONG", "SHORT"]:
        indicators = self._cache.get_indicators(symbol)
        if indicators is None:
            return "LONG"
        if indicators.ema_20 is not None and indicators.ema_50 is not None:
            return "LONG" if indicators.ema_20 > indicators.ema_50 else "SHORT"
        return "LONG"

    def _get_regime(self, symbol: str) -> VolatilityRegime:
        key = f"regime:{symbol}"
        if key in self._cycle_cache:
            cached: VolatilityRegime = self._cycle_cache[key]
            return cached
        indicators = self._cache.get_indicators(symbol)
        atr_history = self._cache.get_atr_history(symbol)
        current_atr = (indicators.atr_14 if indicators else None) or Decimal(0)
        result = self._volatility.detect_regime(current_atr, atr_history)
        self._cycle_cache[key] = result.regime
        return result.regime

    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema:
        indicators = self._cache.get_indicators(symbol)
        if indicators is None:
            msg = f"Indicators not yet available for {symbol}"
            raise RuntimeError(msg)

        return ScoutDependenciesSchema(
            symbol=symbol,
            current_price=self._cache.get_current_price(symbol),
            timeframe=self._timeframe,
            recent_candles=self._recent_candles(symbol),
            indicators=indicators,
            volatility_regime=self._get_regime(symbol),
        )

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema:
        indicators = self._cache.get_indicators(symbol)
        if indicators is None:
            msg = f"Indicators not yet available for {symbol}"
            raise RuntimeError(msg)

        candles = self._cache.get_candles(symbol)
        if not candles:
            msg = f"No candles available for {symbol}"
            raise RuntimeError(msg)

        order_flow = self._cache.get_order_flow(symbol)
        confluence = self._confluence.evaluate(
            self._detect_side(symbol),
            candles[-1],
            indicators,
            order_flow,
        )

        return AnalystDependenciesSchema(
            symbol=symbol,
            current_price=self._cache.get_current_price(symbol),
            timeframe=self._timeframe,
            recent_candles=candles[-ANALYSIS_CANDLES_COUNT:],
            indicators=indicators,
            order_flow=order_flow,
            algorithm_confluence=confluence,
            volatility_regime=self._get_regime(symbol),
        )

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema:
        indicators = self._cache.get_indicators(symbol)
        if indicators is None:
            msg = f"Indicators not yet available for {symbol}"
            raise RuntimeError(msg)

        candles = self._cache.get_candles(symbol)
        if not candles:
            msg = f"No candles available for {symbol}"
            raise RuntimeError(msg)

        order_flow = self._cache.get_order_flow(symbol)
        confluence = self._confluence.evaluate(
            self._detect_side(symbol),
            candles[-1],
            indicators,
            order_flow,
        )

        account_state = await self._get_cached_account_state()
        open_positions = await self._get_cached_positions()

        return TradingDependenciesSchema(
            symbol=symbol,
            current_price=self._cache.get_current_price(symbol),
            timeframe=self._timeframe,
            recent_candles=candles[-ANALYSIS_CANDLES_COUNT:],
            indicators=indicators,
            order_flow=order_flow,
            algorithm_confluence=confluence,
            volatility_regime=self._get_regime(symbol),
            account_state=account_state,
            open_positions=open_positions,
            exchange_client=self._exchange,
            event_store=self._event_store,
            atr_history=self._cache.get_atr_history(symbol),
        )

    async def _get_cached_account_state(self) -> AccountStateSchema:
        key = "account_state"
        if key in self._cycle_cache:
            cached: AccountStateSchema = self._cycle_cache[key]
            return cached
        state = await self._state_manager.get_account_state()
        if state is None:
            msg = "Account state not available"
            raise RuntimeError(msg)
        self._cycle_cache[key] = state
        return state

    async def _get_cached_positions(self) -> list[PositionSchema]:
        key = "open_positions"
        if key in self._cycle_cache:
            cached: list[PositionSchema] = self._cycle_cache[key]
            return cached
        positions = await self._state_manager.get_all_positions()
        self._cycle_cache[key] = positions
        return positions
