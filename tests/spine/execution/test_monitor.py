from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.models import OrderStatus
from kavzi_trader.spine.execution.monitor import OrderMonitor


@pytest.mark.asyncio()
async def test_monitor_returns_filled_order(filled_order_response) -> None:
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(return_value=filled_order_response)
    monitor = OrderMonitor(exchange=exchange, timeout_s=1)

    result = await monitor.wait_for_completion("BTCUSDT", 123)

    assert result is not None
    assert result.status == OrderStatus.FILLED
