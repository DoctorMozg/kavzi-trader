import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.binance.client import BinanceClient

_EPOCH_2024_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z


@pytest.fixture
def new_york_local_tz(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


class TestToMs:
    def test_int_passes_through(self) -> None:
        assert BinanceClient._to_ms(_EPOCH_2024_MS) == _EPOCH_2024_MS

    def test_aware_datetime_converted(self) -> None:
        moment = datetime(2024, 1, 1, tzinfo=UTC)
        assert BinanceClient._to_ms(moment) == _EPOCH_2024_MS

    def test_non_utc_offset_respected(self) -> None:
        moment = datetime(2024, 1, 1, 2, 0, tzinfo=timezone(timedelta(hours=2)))
        assert BinanceClient._to_ms(moment) == _EPOCH_2024_MS

    @pytest.mark.usefixtures("new_york_local_tz")
    def test_naive_datetime_treated_as_utc_not_local(self) -> None:
        naive = datetime(2024, 1, 1)  # noqa: DTZ001 - naive input under test
        assert BinanceClient._to_ms(naive) == _EPOCH_2024_MS


class TestTimeParams:
    def test_omits_missing_bounds(self) -> None:
        assert BinanceClient._time_params(None, None) == {}

    def test_maps_both_bounds(self) -> None:
        params = BinanceClient._time_params(
            datetime(2024, 1, 1, tzinfo=UTC), _EPOCH_2024_MS + 1_000
        )
        assert params == {
            "startTime": _EPOCH_2024_MS,
            "endTime": _EPOCH_2024_MS + 1_000,
        }


@pytest.mark.usefixtures("new_york_local_tz")
async def test_get_klines_sends_naive_datetime_as_utc_ms() -> None:
    client = BinanceClient()
    await client.client.close_connection()
    client.client = AsyncMock()
    client.client.futures_klines.return_value = []

    naive = datetime(2024, 1, 1)  # noqa: DTZ001 - naive input under test
    await client.get_klines("BTCUSDT", "15m", start_time=naive)

    client.client.futures_klines.assert_awaited_once_with(
        symbol="BTCUSDT",
        interval="15m",
        limit=500,
        startTime=_EPOCH_2024_MS,
    )
