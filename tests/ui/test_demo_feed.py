import pytest

from kavzi_trader.ui.demo_feed import UiDemoFeed
from kavzi_trader.ui.event_schemas import UiEvent


class _CollectingPublisher:
    def __init__(self) -> None:
        self.events: list[UiEvent] = []

    async def publish(self, event: UiEvent) -> None:
        self.events.append(event)


class TestUiDemoFeed:
    async def test_backfill_then_account_ticks(self) -> None:
        publisher = _CollectingPublisher()
        feed = UiDemoFeed(publisher, ["BTCUSDT", "ETHUSDT"], seed=7)

        await feed._backfill()
        await feed._publish_account()

        types = [e.type for e in publisher.events]
        assert types == ["candles", "candles", "account"]

    def test_rejects_empty_symbols(self) -> None:
        with pytest.raises(ValueError, match="at least one symbol"):
            UiDemoFeed(_CollectingPublisher(), [])
