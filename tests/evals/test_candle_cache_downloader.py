from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.kline_downloader import KlineDownloader

STEP_MS = 900_000
START = 1_700_000_100_000 - 1_700_000_100_000 % STEP_MS


def _candle(open_ms: int) -> CandlestickSchema:
    price = Decimal(100) + Decimal(open_ms % 7)
    return CandlestickSchema(
        open_time=datetime.fromtimestamp(open_ms / 1000, UTC),
        open_price=price,
        high_price=price + 1,
        low_price=price - 1,
        close_price=price,
        volume=Decimal(1),
        close_time=datetime.fromtimestamp((open_ms + STEP_MS - 1) / 1000, UTC),
        quote_volume=Decimal(100),
        trades_count=3,
        taker_buy_base_volume=Decimal(1),
        taker_buy_quote_volume=Decimal(50),
        interval="15m",
        symbol="AAA",
    )


class FakeClient:
    """Serves a deterministic candle series in pages like the exchange does."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    async def get_klines(
        self, symbol: str, interval: str, start_time: int, end_time: int, limit: int
    ) -> list[CandlestickSchema]:
        self.calls.append((start_time, end_time, limit))
        first = start_time + (-start_time) % STEP_MS
        times = range(first, end_time + 1, STEP_MS)
        return [_candle(t) for t in list(times)[:limit]]


@pytest.fixture
def cache(tmp_path: Path) -> CandleCache:
    return CandleCache(tmp_path / "eval_cache", "15m")


class TestKlineDownloader:
    async def test_paginates_and_fills_range(self, cache: CandleCache) -> None:
        client = FakeClient()
        end = START + 3200 * STEP_MS
        await KlineDownloader(
            cast("ExchangeClient", client), cache, "15m"
        ).ensure_range("AAA", START, end)
        frame = cache.load("AAA")
        assert len(frame) == 3200
        assert frame["open_time_ms"].is_monotonic_increasing
        assert len(client.calls) == 3
        assert all(limit == 1500 for _, _, limit in client.calls)

    # An off-grid start used to refetch the sub-step head gap on every rerun.
    @pytest.mark.parametrize("offset_ms", [0, STEP_MS // 3])
    async def test_rerun_downloads_nothing(
        self, cache: CandleCache, offset_ms: int
    ) -> None:
        client = FakeClient()
        downloader = KlineDownloader(cast("ExchangeClient", client), cache, "15m")
        start = START - offset_ms
        end = START + 100 * STEP_MS
        await downloader.ensure_range("AAA", start, end)
        client.calls.clear()
        await downloader.ensure_range("AAA", start, end)
        assert client.calls == []
        assert len(cache.load("AAA")) == 100

    async def test_extends_cache_at_both_ends_without_duplicates(
        self, cache: CandleCache
    ) -> None:
        client = FakeClient()
        downloader = KlineDownloader(cast("ExchangeClient", client), cache, "15m")
        await downloader.ensure_range(
            "AAA", START + 50 * STEP_MS, START + 100 * STEP_MS
        )
        await downloader.ensure_range("AAA", START, START + 150 * STEP_MS)
        frame = cache.load("AAA")
        assert len(frame) == 150
        assert frame["open_time_ms"].is_unique
        assert frame["open_time_ms"].iloc[0] == START

    async def test_rejects_empty_range(self, cache: CandleCache) -> None:
        with pytest.raises(ValueError, match="empty range"):
            await KlineDownloader(
                cast("ExchangeClient", FakeClient()), cache, "15m"
            ).ensure_range("AAA", START, START)
