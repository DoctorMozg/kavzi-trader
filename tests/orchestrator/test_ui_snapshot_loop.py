from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.orchestrator.loops.ui_snapshot import UiSnapshotLoop
from kavzi_trader.spine.state.schemas import AccountStateSchema
from kavzi_trader.ui.config import UiConfigSchema
from kavzi_trader.ui.event_schemas import (
    UiAccountEventSchema,
    UiCandlesEventSchema,
)
from kavzi_trader.ui.recorder import UiEventRecorder
from tests.ui.factories import CollectingUiPublisher

T0 = datetime(2026, 11, 14, tzinfo=UTC)


def _candle(index: int) -> CandlestickSchema:
    open_time = T0 + timedelta(minutes=15 * index)
    return CandlestickSchema(
        open_time=open_time,
        open_price=Decimal(100),
        high_price=Decimal(101),
        low_price=Decimal(99),
        close_price=Decimal(100),
        volume=Decimal(5),
        close_time=open_time + timedelta(minutes=15),
        quote_volume=Decimal(500),
        trades_count=10,
        taker_buy_base_volume=Decimal(2),
        taker_buy_quote_volume=Decimal(200),
        interval="15m",
        symbol="BTCUSDT",
    )


class _MarketData:
    def __init__(self) -> None:
        self.candles = [_candle(i) for i in range(5)]

    def get_current_price(self, symbol: str) -> Decimal:
        return Decimal(100) if symbol == "BTCUSDT" else Decimal(0)

    def get_candles(self, symbol: str) -> list[CandlestickSchema]:
        return list(self.candles) if symbol == "BTCUSDT" else []


class _Harness:
    def __init__(self, account: AccountStateSchema | None) -> None:
        self.publisher = CollectingUiPublisher()
        self.market = _MarketData()
        state = AsyncMock()
        state.get_account_state = AsyncMock(return_value=account)
        state.get_all_positions = AsyncMock(return_value=[])
        self.loop = UiSnapshotLoop(
            recorder=UiEventRecorder(
                self.publisher,
                initial_balance_usdt=Decimal(1000),
                is_paper=True,
            ),
            state_manager=state,
            market_data=self.market,
            symbols=["BTCUSDT", "ETHUSDT"],
            config=UiConfigSchema(backfill_candles=3),
        )

    def candle_batches(self) -> list[list[int]]:
        return [
            [c.open_time_ms for c in e.candles]
            for e in self.publisher.events
            if isinstance(e, UiCandlesEventSchema)
        ]


@pytest.fixture
def account() -> AccountStateSchema:
    return AccountStateSchema(
        total_balance_usdt=Decimal(1000),
        available_balance_usdt=Decimal(1000),
        locked_balance_usdt=Decimal(0),
        peak_balance=Decimal(1000),
        updated_at=T0,
    )


class TestUiSnapshotLoop:
    async def test_first_tick_backfills_then_only_new_closes(
        self,
        account: AccountStateSchema,
    ) -> None:
        harness = _Harness(account)

        await harness.loop.publish_once(["ingest"])
        await harness.loop.publish_once(["ingest"])
        harness.market.candles.append(_candle(5))
        await harness.loop.publish_once(["ingest"])

        batches = harness.candle_batches()
        assert len(batches) == 2
        assert len(batches[0]) == 3
        assert batches[1] == [int(_candle(5).open_time.timestamp() * 1000)]

    async def test_account_tick_only_prices_known_symbols(
        self,
        account: AccountStateSchema,
    ) -> None:
        harness = _Harness(account)

        await harness.loop.publish_once(["ingest", "reasoning"])

        accounts = [
            e for e in harness.publisher.events if isinstance(e, UiAccountEventSchema)
        ]
        assert len(accounts) == 1
        assert accounts[0].prices == {"BTCUSDT": Decimal(100)}
        assert accounts[0].running_loops == ["ingest", "reasoning"]

    async def test_no_account_state_skips_account_but_still_sends_candles(self) -> None:
        harness = _Harness(account=None)

        await harness.loop.publish_once([])

        assert [e.type for e in harness.publisher.events] == ["candles"]
