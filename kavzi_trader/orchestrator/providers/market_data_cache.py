import asyncio
import collections
import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema

logger = logging.getLogger(__name__)

DEFAULT_MAX_CANDLES = 500
ATR_HISTORY_LENGTH = 30


class _SymbolCache:
    """Mutable per-symbol market data bucket."""

    __slots__ = (
        "atr_history",
        "atr_pct_history",
        "candles",
        "current_price",
        "indicators",
        "order_flow",
    )

    def __init__(self, max_candles: int) -> None:
        self.candles: collections.deque[CandlestickSchema] = collections.deque(
            maxlen=max_candles,
        )
        self.indicators: TechnicalIndicatorsSchema | None = None
        self.order_flow: OrderFlowSchema | None = None
        self.current_price: Decimal = Decimal(0)
        self.atr_history: collections.deque[Decimal] = collections.deque(
            maxlen=ATR_HISTORY_LENGTH,
        )
        # Parallel rolling window of ATR expressed as % of close price.
        # Powers the adaptive per-symbol ATR percentile gate in the Scout
        # filter so thresholds track each symbol's own recent volatility
        # rather than a hardcoded global floor.
        self.atr_pct_history: collections.deque[Decimal] = collections.deque(
            maxlen=ATR_HISTORY_LENGTH,
        )


class MarketDataCache:
    """Shared in-memory per-symbol cache for candles, indicators, and order flow."""

    def __init__(
        self,
        symbols: list[str],
        indicator_calculator: TechnicalIndicatorCalculator,
        max_candles: int = DEFAULT_MAX_CANDLES,
    ) -> None:
        self._calculator = indicator_calculator
        self._max_candles = max_candles
        self._caches: dict[str, _SymbolCache] = {
            s: _SymbolCache(max_candles) for s in symbols
        }
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Initialisation (REST backfill)
    # ------------------------------------------------------------------

    async def initialize(
        self,
        exchange: BinanceClient,
        interval: str,
    ) -> None:
        """Load historical candles via REST and compute initial indicators."""
        for symbol, cache in self._caches.items():
            try:
                candles = await exchange.get_klines(
                    symbol,
                    interval,
                    limit=self._max_candles,
                )
                if not candles:
                    logger.warning(
                        "No historical candles returned for %s",
                        symbol,
                    )
                    continue
                cache.candles.extend(candles)
                cache.current_price = candles[-1].close_price
                self._recompute_indicators(cache)
                self._seed_atr_history(cache)
                logger.info(
                    "Cache initialised for %s: %d candles, price=%s, atr=%s",
                    symbol,
                    len(cache.candles),
                    cache.current_price,
                    cache.indicators.atr_14 if cache.indicators else "N/A",
                )
            except Exception:
                logger.exception(
                    "Failed to initialise cache for %s",
                    symbol,
                )

    # ------------------------------------------------------------------
    # Write methods (called from callbacks / fetchers)
    # ------------------------------------------------------------------

    async def update_candle(
        self,
        symbol: str,
        candle: CandlestickSchema,
        *,
        is_closed: bool,
    ) -> None:
        cache = self._caches.get(symbol)
        if cache is None:
            return
        async with self._lock:
            cache.current_price = candle.close_price
            if is_closed:
                if cache.candles and cache.candles[-1].open_time == candle.open_time:
                    cache.candles[-1] = candle
                else:
                    cache.candles.append(candle)
                self._recompute_indicators(cache)
                if cache.indicators and cache.indicators.atr_14 is not None:
                    cache.atr_history.append(cache.indicators.atr_14)
                    if candle.close_price > 0:
                        atr_pct = (
                            cache.indicators.atr_14 / candle.close_price * Decimal(100)
                        )
                        cache.atr_pct_history.append(atr_pct)

    async def update_price(self, symbol: str, price: Decimal) -> None:
        cache = self._caches.get(symbol)
        if cache is None:
            return
        cache.current_price = price

    async def update_order_flow(
        self,
        symbol: str,
        order_flow: OrderFlowSchema,
    ) -> None:
        cache = self._caches.get(symbol)
        if cache is None:
            return
        cache.order_flow = order_flow

    # ------------------------------------------------------------------
    # Read methods (called from providers)
    # ------------------------------------------------------------------

    def get_candles(self, symbol: str) -> list[CandlestickSchema]:
        cache = self._caches.get(symbol)
        if cache is None:
            return []
        return list(cache.candles)

    def get_indicators(
        self,
        symbol: str,
    ) -> TechnicalIndicatorsSchema | None:
        cache = self._caches.get(symbol)
        if cache is None:
            return None
        return cache.indicators

    def get_order_flow(self, symbol: str) -> OrderFlowSchema | None:
        cache = self._caches.get(symbol)
        if cache is None:
            return None
        return cache.order_flow

    def get_current_price(self, symbol: str) -> Decimal:
        cache = self._caches.get(symbol)
        if cache is None:
            return Decimal(0)
        return cache.current_price

    def get_atr(self, symbol: str) -> Decimal:
        cache = self._caches.get(symbol)
        if cache is None or cache.indicators is None:
            return Decimal(0)
        return cache.indicators.atr_14 or Decimal(0)

    def get_atr_history(self, symbol: str) -> list[Decimal]:
        cache = self._caches.get(symbol)
        if cache is None:
            return []
        return list(cache.atr_history)

    def get_atr_pct_history(self, symbol: str) -> list[Decimal]:
        cache = self._caches.get(symbol)
        if cache is None:
            return []
        return list(cache.atr_pct_history)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recompute_indicators(self, cache: _SymbolCache) -> None:
        candles = list(cache.candles)
        if not candles:
            return
        cache.indicators = self._calculator.calculate(candles)

    def _seed_atr_history(self, cache: _SymbolCache) -> None:
        """Build initial ATR and ATR% histories from progressive candle windows."""
        candles = list(cache.candles)
        if len(candles) < ATR_HISTORY_LENGTH:
            if cache.indicators and cache.indicators.atr_14 is not None:
                cache.atr_history.append(cache.indicators.atr_14)
                last_close = candles[-1].close_price if candles else Decimal(0)
                if last_close > 0:
                    cache.atr_pct_history.append(
                        cache.indicators.atr_14 / last_close * Decimal(100),
                    )
            return
        start = len(candles) - ATR_HISTORY_LENGTH
        for i in range(ATR_HISTORY_LENGTH):
            window = candles[: start + i + 1]
            result = self._calculator.calculate(window)
            if result and result.atr_14 is not None:
                cache.atr_history.append(result.atr_14)
                window_close = window[-1].close_price
                if window_close > 0:
                    cache.atr_pct_history.append(
                        result.atr_14 / window_close * Decimal(100),
                    )
        logger.debug(
            "Seeded ATR history with %d entries (atr_pct=%d entries)",
            len(cache.atr_history),
            len(cache.atr_pct_history),
        )
