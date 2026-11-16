from datetime import UTC, datetime

import pytest

from kavzi_trader.commons.sim_clock import SimClock

_START_MS = 1_609_459_200_000


def test_now_matches_now_ms() -> None:
    clock = SimClock(_START_MS)
    clock.advance_to(_START_MS + 90_000)

    assert clock.now_ms() == _START_MS + 90_000
    assert clock.now() == datetime(2021, 1, 1, 0, 1, 30, tzinfo=UTC)


def test_rejects_moving_backwards() -> None:
    clock = SimClock(_START_MS)

    with pytest.raises(ValueError, match="backwards"):
        clock.advance_to(_START_MS - 1)
    assert clock.now_ms() == _START_MS
