from pathlib import Path

import httpx2
import pytest

from kavzi_trader.evals import dvol_history
from kavzi_trader.evals.dvol_history import DvolHistory
from tests.archive.conftest import NO_WAIT

DAY_MS = 86_400_000
START_MS = 1_640_995_200_000  # 2022-01-01


def _handler(request: httpx2.Request) -> httpx2.Response:
    end = int(request.url.params["end_timestamp"])
    # Two pages, newest first, as Deribit pages backwards with `continuation`.
    if end > START_MS + 2 * DAY_MS:
        days, continuation = [2, 3], START_MS + 2 * DAY_MS
    else:
        days, continuation = [0, 1], None
    data = [[START_MS + d * DAY_MS, 0, 0, 0, 50.0 + d] for d in days]
    return httpx2.Response(
        200, json={"result": {"data": data, "continuation": continuation}}
    )


class TestDvolHistory:
    async def test_follows_continuation_and_round_trips_through_csv(
        self, tmp_path: Path
    ) -> None:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(_handler)) as http:
            series = await DvolHistory(http).download(
                "BTC", START_MS, START_MS + 4 * DAY_MS
            )

        DvolHistory.save(series, tmp_path)
        loaded = DvolHistory.load("BTC", tmp_path)

        assert list(series) == [50.0, 51.0, 52.0, 53.0]
        assert str(series.index[0].date()) == "2022-01-01"
        assert list(loaded) == list(series)
        assert (loaded.index == series.index).all()

    async def test_server_error_is_raised_after_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dvol_history, "_RETRY", NO_WAIT)
        failing = httpx2.MockTransport(lambda _: httpx2.Response(503))
        async with httpx2.AsyncClient(transport=failing) as http:
            with pytest.raises(httpx2.HTTPStatusError):
                await DvolHistory(http).download("BTC", START_MS, START_MS + DAY_MS)
