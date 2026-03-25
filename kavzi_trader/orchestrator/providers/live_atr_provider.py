from decimal import Decimal

from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache


class LiveAtrProvider:
    """Reads the latest ATR from the shared market data cache."""

    def __init__(self, cache: MarketDataCache) -> None:
        self._cache = cache

    async def get_atr(self, symbol: str) -> Decimal:
        return self._cache.get_atr(symbol)
