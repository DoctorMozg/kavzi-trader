from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.api.binance.schemas.data_dicts import FundingRateDict
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.funding_cache import FundingCache
from kavzi_trader.evals.funding_downloader import FundingDownloader
from kavzi_trader.evals.market_feature_builder import MarketFeatureBuilder
from kavzi_trader.evals.signal_sampler import FUNDING_SIGNAL, SignalSampler
from kavzi_trader.order_flow.funding import calculate_funding_zscore
from kavzi_trader.order_flow.schemas import FundingRateSchema
from tests.evals.frames import BASE_MS, STEP_MS, make_frame

SETTLE_MS = 8 * 3600 * 1000
HISTORY = 300


def settlement_rate(ms: int) -> float:
    return 0.0001 * (1 + (ms // SETTLE_MS) % 5)


class FakeFundingClient:
    """Serves an 8h settlement schedule in pages, like GET /fapi/v1/fundingRate."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    async def get_funding_rate(
        self, symbol: str, limit: int, start_time: int, end_time: int
    ) -> list[FundingRateDict]:
        self.calls.append((start_time, end_time, limit))
        first = start_time + (-start_time) % SETTLE_MS
        times = list(range(first, end_time + 1, SETTLE_MS))[:limit]
        return [
            FundingRateDict(
                symbol=symbol, fundingRate=str(settlement_rate(t)), fundingTime=t
            )
            for t in times
        ]


def settlements(start_ms: int, count: int) -> pd.DataFrame:
    times = start_ms - start_ms % SETTLE_MS + SETTLE_MS * np.arange(count)
    return pd.DataFrame(
        {
            "funding_time_ms": times.astype(np.int64),
            "funding_rate": [settlement_rate(int(t)) for t in times],
        }
    )


@pytest.fixture
def cache(tmp_path: Path) -> FundingCache:
    return FundingCache(tmp_path / "cache")


class TestFundingDownloader:
    async def test_pages_and_fills_the_range(self, cache: FundingCache) -> None:
        client = FakeFundingClient()
        end = BASE_MS + 1500 * SETTLE_MS

        await FundingDownloader(cast("ExchangeClient", client), cache).ensure_range(
            "AAA", BASE_MS, end
        )

        frame = cache.load("AAA")
        assert len(frame) == 1500
        assert frame["funding_time_ms"].is_monotonic_increasing
        assert [c[2] for c in client.calls] == [1000, 1000]

    async def test_rerun_fetches_only_the_tail(self, cache: FundingCache) -> None:
        client = FakeFundingClient()
        downloader = FundingDownloader(cast("ExchangeClient", client), cache)
        await downloader.ensure_range("AAA", BASE_MS, BASE_MS + 10 * SETTLE_MS)
        client.calls.clear()

        await downloader.ensure_range("AAA", BASE_MS, BASE_MS + 20 * SETTLE_MS)

        assert len(cache.load("AAA")) == 20
        assert len(client.calls) == 1
        assert client.calls[0][0] > BASE_MS + 9 * SETTLE_MS

    async def test_fetches_a_head_gap_longer_than_a_settlement(
        self, cache: FundingCache
    ) -> None:
        client = FakeFundingClient()
        downloader = FundingDownloader(cast("ExchangeClient", client), cache)
        await downloader.ensure_range("AAA", BASE_MS, BASE_MS + 10 * SETTLE_MS)
        client.calls.clear()

        earlier = BASE_MS - 5 * SETTLE_MS
        await downloader.ensure_range("AAA", earlier, BASE_MS + 10 * SETTLE_MS)

        assert client.calls[0][0] == earlier
        assert len(cache.load("AAA")) == 15

    async def test_rejects_an_empty_range(self, cache: FundingCache) -> None:
        with pytest.raises(ValueError, match="empty range"):
            await FundingDownloader(
                cast("ExchangeClient", FakeFundingClient()), cache
            ).ensure_range("AAA", BASE_MS, BASE_MS)

    def test_missing_file_loads_empty(self, cache: FundingCache) -> None:
        assert cache.load("NONE").empty


class TestSamplerFunding:
    @pytest.fixture
    def sampler(self, app_config: AppConfig) -> SignalSampler:
        return SignalSampler(MarketFeatureBuilder(app_config.risk), HISTORY, stride=41)

    def test_matches_live_zscore_without_look_ahead(
        self, sampler: SignalSampler
    ) -> None:
        frame = make_frame(HISTORY + 150, seed=2)
        funding = settlements(BASE_MS - 150 * SETTLE_MS, 200)

        samples = sampler.sample("AAA", frame, max_horizon=10, funding=funding)

        assert len(samples) > 1
        for row in samples.itertuples():
            close_ms = int(frame["close_time_ms"].iloc[int(row.idx)])
            settled = funding[funding["funding_time_ms"] <= close_ms].tail(100)
            live = calculate_funding_zscore(
                [
                    FundingRateSchema(
                        symbol="AAA",
                        funding_rate=Decimal(str(r.funding_rate)),
                        funding_time=datetime.fromtimestamp(
                            r.funding_time_ms / 1000, UTC
                        ),
                    )
                    for r in settled.itertuples()
                ]
            )
            assert live is not None
            assert row.funding_z == float(live.funding_zscore)
            assert getattr(row, f"LONG_{FUNDING_SIGNAL}") == (live.funding_zscore <= 0)
            assert getattr(row, f"SHORT_{FUNDING_SIGNAL}") == (live.funding_zscore >= 0)

    def test_bars_before_two_settlements_have_no_signal(
        self, sampler: SignalSampler
    ) -> None:
        frame = make_frame(HISTORY + 100)
        late = settlements(BASE_MS + (HISTORY + 90) * STEP_MS, 3)

        samples = sampler.sample("AAA", frame, max_horizon=10, funding=late)

        assert samples["funding_z"].isna().all()
        assert not samples[f"LONG_{FUNDING_SIGNAL}"].any()
        assert not samples[f"SHORT_{FUNDING_SIGNAL}"].any()

    def test_without_funding_there_is_no_funding_column(
        self, sampler: SignalSampler
    ) -> None:
        samples = sampler.sample("AAA", make_frame(HISTORY + 60), max_horizon=10)
        assert f"LONG_{FUNDING_SIGNAL}" not in samples
        assert "funding_z" not in samples
