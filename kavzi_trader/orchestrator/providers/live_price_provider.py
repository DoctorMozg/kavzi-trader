from decimal import Decimal

from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache


class LivePriceProvider:
    """Reads the latest price from the shared market data cache."""

    def __init__(self, cache: MarketDataCache) -> None:
        self._cache = cache

    async def get_current_price(self, symbol: str) -> Decimal:
        return self._cache.get_current_price(symbol)
