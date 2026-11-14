from decimal import Decimal

import pytest

from kavzi_trader.ui.config import UiConfigSchema
from kavzi_trader.ui.server.projection import UiStateProjection
from tests.ui.factories import (
    make_account,
    make_candles,
    make_close,
    make_decision,
    make_trade,
)


@pytest.fixture
def projection() -> UiStateProjection:
    return UiStateProjection(
        UiConfigSchema(max_decisions=10, max_trades=10, max_candles=10),
    )


class TestUiStateProjection:
    def test_empty_snapshot(self, projection: UiStateProjection) -> None:
        message = projection.snapshot_message()

        assert message.seq == 0
        assert message.snapshot.account is None
        assert message.snapshot.decisions == []

    def test_apply_assigns_consecutive_seq(self, projection: UiStateProjection) -> None:
        seqs = [projection.apply(make_decision()), projection.apply(make_trade())]

        assert seqs == [1, 2]
        assert projection.snapshot_message().seq == 2

    def test_account_replaces_previous(self, projection: UiStateProjection) -> None:
        projection.apply(make_account(balance="1000"))
        projection.apply(make_account(balance="1100"))

        account = projection.snapshot_message().snapshot.account
        assert account is not None
        assert account.balance_usdt == Decimal(1100)

    def test_lists_keep_newest_within_cap(self, projection: UiStateProjection) -> None:
        for ts_ms in range(15):
            projection.apply(make_decision(ts_ms=ts_ms))
        projection.apply(make_trade())
        projection.apply(make_close())

        snapshot = projection.snapshot_message().snapshot
        assert [d.ts_ms for d in snapshot.decisions] == list(range(5, 15))
        assert len(snapshot.trades) == 1
        assert len(snapshot.closed_positions) == 1

    def test_candles_merge_by_open_time_sorted(
        self,
        projection: UiStateProjection,
    ) -> None:
        projection.apply(make_candles([300, 100, 200]))
        projection.apply(make_candles([200, 400]))

        snapshot = projection.snapshot_message().snapshot
        assert [c.open_time_ms for c in snapshot.candles["BTCUSDT"]] == [
            100,
            200,
            300,
            400,
        ]
        assert snapshot.candle_interval == "15m"

    def test_candles_trim_oldest_over_cap(self, projection: UiStateProjection) -> None:
        projection.apply(make_candles(list(range(12))))
        projection.apply(make_candles([5], symbol="ETHUSDT"))

        candles = projection.snapshot_message().snapshot.candles
        assert [c.open_time_ms for c in candles["BTCUSDT"]] == list(range(2, 12))
        assert len(candles["ETHUSDT"]) == 1
