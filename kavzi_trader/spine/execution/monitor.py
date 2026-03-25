import asyncio
import logging

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import OrderResponseSchema, OrderStatus

logger = logging.getLogger(__name__)


class OrderMonitor:
    """Polls exchange order status until completion or timeout."""

    def __init__(self, exchange: BinanceClient, timeout_s: int) -> None:
        self._exchange = exchange
        self._timeout_s = timeout_s

    async def wait_for_completion(
        self,
        symbol: str,
        order_id: int,
    ) -> OrderResponseSchema | None:
        logger.debug(
            "Monitoring order %s for %s, timeout=%ds",
            order_id, symbol, self._timeout_s,
        )
        try:
            result = await asyncio.wait_for(
                self._poll_status(symbol, order_id),
                timeout=self._timeout_s,
            )
            logger.info(
                "Order %s for %s completed: status=%s",
                order_id, symbol, result.status.value,
                extra={"symbol": symbol},
            )
            return result
        except TimeoutError:
            logger.warning(
                "Order %s for %s not completed within %ds",
                order_id,
                symbol,
                self._timeout_s,
            )
            return None

    async def _poll_status(self, symbol: str, order_id: int) -> OrderResponseSchema:
        while True:
            order = await self._exchange.get_order(symbol=symbol, order_id=order_id)
            if order.status in {OrderStatus.FILLED, OrderStatus.CANCELED}:
                return order
            await asyncio.sleep(1)
