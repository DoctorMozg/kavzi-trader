import logging
from datetime import timedelta
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.commons.time_utility import milliseconds_to_datetime
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.order_flow.calculator import OrderFlowCalculator
from kavzi_trader.order_flow.schemas import (
    FundingRateSchema,
    LongShortRatioSchema,
    OpenInterestSchema,
)

logger = logging.getLogger(__name__)

ONE_HOUR = timedelta(hours=1)


class LiveOrderFlowFetcher:
    """Periodically fetches order flow data from Binance REST and updates the cache."""

    def __init__(
        self,
        exchange: BinanceClient,
        cache: MarketDataCache,
        calculator: OrderFlowCalculator,
        symbols: list[str],
    ) -> None:
        self._exchange = exchange
        self._cache = cache
        self._calculator = calculator
        self._symbols = symbols

    async def fetch(self) -> None:
        for symbol in self._symbols:
            try:
                await self._fetch_symbol(symbol)
            except Exception:
                logger.exception(
                    "Failed to fetch order flow for %s, continuing",
                    symbol,
                    extra={"symbol": symbol},
                )

    async def _fetch_symbol(self, symbol: str) -> None:
        raw_funding = await self._exchange.get_funding_rate(
            symbol, limit=100,
        )
        funding_rates = [
            FundingRateSchema(
                symbol=symbol,
                funding_rate=Decimal(str(d["fundingRate"])),
                funding_time=milliseconds_to_datetime(int(d["fundingTime"])),
                mark_price=Decimal(str(d["markPrice"]))
                if d.get("markPrice")
                else None,
            )
            for d in raw_funding
        ]

        raw_oi = await self._exchange.get_open_interest_history(
            symbol, period="15m", limit=30,
        )
        oi_history = [
            OpenInterestSchema(
                symbol=symbol,
                open_interest=Decimal(str(d["sumOpenInterest"])),
                timestamp=milliseconds_to_datetime(int(d["timestamp"])),
            )
            for d in raw_oi
        ]

        raw_ls = await self._exchange.get_long_short_ratio(
            symbol, period="15m", limit=1,
        )
        ls_ratio: LongShortRatioSchema | None = None
        if raw_ls:
            d = raw_ls[0]
            ls_ratio = LongShortRatioSchema(
                symbol=symbol,
                long_short_ratio=Decimal(str(d["longShortRatio"])),
                long_account_percent=Decimal(str(d["longAccount"])),
                short_account_percent=Decimal(str(d["shortAccount"])),
                timestamp=milliseconds_to_datetime(int(d["timestamp"])),
            )

        price_change_1h = self._calculate_price_change_1h(symbol)

        order_flow = self._calculator.calculate(
            symbol=symbol,
            funding_rates=funding_rates,
            oi_history=oi_history,
            long_short_ratio=ls_ratio,
            price_change_1h_percent=price_change_1h,
        )
        if order_flow is not None:
            await self._cache.update_order_flow(symbol, order_flow)
            logger.debug(
                "Order flow updated for %s: funding_rate=%s oi=%s",
                symbol,
                order_flow.funding_rate,
                order_flow.open_interest,
                extra={"symbol": symbol},
            )
        else:
            logger.warning(
                "Order flow calculation returned None for %s", symbol,
                extra={"symbol": symbol},
            )

    def _calculate_price_change_1h(self, symbol: str) -> Decimal | None:
        candles = self._cache.get_candles(symbol)
        if len(candles) < 2:
            return None

        current_candle = candles[-1]
        target_close_time = current_candle.close_time - ONE_HOUR

        for candle in reversed(candles[:-1]):
            if candle.close_time == target_close_time:
                if candle.close_price <= 0:
                    return None
                return (
                    (current_candle.close_price - candle.close_price)
                    / candle.close_price
                    * 100
                )

        return None
