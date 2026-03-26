import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.api.binance.schemas.data_dicts import KlineData, TickerData
from kavzi_trader.api.binance.websocket.client import BinanceWebsocketClient
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache

logger = logging.getLogger(__name__)

CONNECTION_CHECK_INTERVAL_S = 5


class LiveStreamManager:
    """Wraps BinanceWebsocketClient and feeds kline/ticker data into the cache."""

    def __init__(
        self,
        ws_client: BinanceWebsocketClient,
        cache: MarketDataCache,
        symbols: list[str],
        interval: str,
    ) -> None:
        self._ws_client = ws_client
        self._cache = cache
        self._symbols = symbols
        self._interval = interval

    async def start(self) -> None:
        logger.info(
            "LiveStreamManager starting for %d symbols on %s",
            len(self._symbols),
            self._interval,
        )
        await self._ws_client.start()
        for symbol in self._symbols:
            await self._ws_client.subscribe_kline_stream(
                symbol,
                self._interval,
                self._on_kline,
            )
            await self._ws_client.subscribe_ticker_stream(
                symbol,
                self._on_ticker,
            )
            logger.info("Subscribed to streams for %s", symbol)

        while self._ws_client.is_connected():
            await asyncio.sleep(CONNECTION_CHECK_INTERVAL_S)

        logger.warning("WebSocket disconnected, stopping stream manager")
        await self._ws_client.stop()

    async def _on_kline(self, data: KlineData) -> None:
        try:
            k = data["k"]
            symbol: str = k["s"]  # type: ignore[assignment]
            is_closed: bool = k["x"]  # type: ignore[assignment]

            open_time_ms: int = k["t"]  # type: ignore[assignment]
            close_time_ms: int = k["T"]  # type: ignore[assignment]

            candle = CandlestickSchema.model_validate(
                {
                    "open_time": datetime.fromtimestamp(
                        open_time_ms / 1000,
                        UTC,
                    ),
                    "close_time": datetime.fromtimestamp(
                        close_time_ms / 1000,
                        UTC,
                    ),
                    "open_price": Decimal(str(k["o"])),
                    "high_price": Decimal(str(k["h"])),
                    "low_price": Decimal(str(k["l"])),
                    "close_price": Decimal(str(k["c"])),
                    "volume": Decimal(str(k["v"])),
                    "quote_volume": Decimal(str(k["q"])),
                    "trades_count": int(k["n"]),  # type: ignore[arg-type]
                    "taker_buy_base_volume": Decimal(str(k["V"])),
                    "taker_buy_quote_volume": Decimal(str(k["Q"])),
                    "interval": str(k["i"]),
                    "symbol": symbol,
                },
            )
            await self._cache.update_candle(
                symbol,
                candle,
                is_closed=is_closed,
            )
            if is_closed:
                logger.info(
                    "Candle closed for %s: close=%s volume=%s",
                    symbol,
                    candle.close_price,
                    candle.volume,
                )
        except Exception:
            logger.exception("Error processing kline data")

    async def _on_ticker(self, data: TickerData) -> None:
        try:
            symbol = data["s"]
            price = Decimal(data["c"])
            await self._cache.update_price(symbol, price)
        except Exception:
            logger.exception("Error processing ticker data")
