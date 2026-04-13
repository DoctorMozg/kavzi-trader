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
            order_id,
            symbol,
            self._timeout_s,
        )
        try:
            result = await asyncio.wait_for(
                self._poll_status(symbol, order_id),
                timeout=self._timeout_s,
            )
        except TimeoutError:
            logger.warning(
                "Order %s for %s not completed within %ds; reconciliation required",
                order_id,
                symbol,
                self._timeout_s,
                extra={
                    "needs_reconciliation": True,
                    "symbol": symbol,
                    "order_id": order_id,
                },
            )
            return None
        logger.info(
            "Order %s for %s completed: status=%s",
            order_id,
            symbol,
            result.status.value,
            extra={"symbol": symbol},
        )
        return result

    async def _poll_status(self, symbol: str, order_id: int) -> OrderResponseSchema:
        # Exponential backoff with a 30s cap. `failure_count` grows only on
        # poll exceptions (e.g., rate limits) and resets after any successful
        # call, so healthy polls stay at the 1s floor.
        failure_count = 0
        while True:
            try:
                order = await self._exchange.get_order(
                    symbol=symbol,
                    order_id=order_id,
                )
                if order.status in {OrderStatus.FILLED, OrderStatus.CANCELED}:
                    return order
                failure_count = 0
            except Exception:
                logger.exception(
                    "Failed to poll order %s for %s, retrying",
                    order_id,
                    symbol,
                )
                failure_count += 1
            delay_s = min(30, 2**failure_count)
            await asyncio.sleep(delay_s)
