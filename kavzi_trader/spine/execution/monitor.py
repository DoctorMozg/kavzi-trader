import asyncio
import logging
import sys

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.commons.retry import RetryPolicySchema, retry_async
from kavzi_trader.domain.order_enums import OrderStatus
from kavzi_trader.domain.order_response import OrderResponseSchema

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.EXPIRED,
        OrderStatus.REJECTED,
    },
)

_POLL_INTERVAL_S = 1

# Errors back off 2s, 4s, ... capped at 30s. Attempts are unbounded because
# wait_for() in wait_for_completion enforces the overall timeout.
_POLL_RETRY_POLICY = RetryPolicySchema(
    attempts=sys.maxsize,
    backoff_base_s=2,
    retry_on=(Exception,),
    max_delay_s=30,
)


class OrderMonitor:
    """Polls exchange order status until completion or timeout."""

    def __init__(self, exchange: ExchangeClient, timeout_s: int) -> None:
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
        while True:
            order = await retry_async(
                lambda: self._exchange.get_order(symbol=symbol, order_id=order_id),
                _POLL_RETRY_POLICY,
                name=f"Polling order {order_id} for {symbol}",
            )
            if order.status in _TERMINAL_STATUSES:
                return order
            await asyncio.sleep(_POLL_INTERVAL_S)
