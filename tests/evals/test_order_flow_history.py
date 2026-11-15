from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.funding_downloader import FundingDownloader
from kavzi_trader.evals.market_feature_builder import MarketFeatureBuilder
from kavzi_trader.evals.oi_downloader import OiDownloader
from kavzi_trader.evals.series_cache import TIME, VALUE, SeriesCache
from kavzi_trader.evals.signal_sampler import (
    FUNDING_SIGNAL,
    OI_SIGNALS,
    SignalSampler,
)
from kavzi_trader.order_flow.calculator import OrderFlowCalculator
from kavzi_trader.order_flow.funding import calculate_funding_zscore
from kavzi_trader.order_flow.schemas import FundingRateSchema, OpenInterestSchema
from tests.evals.fake_exchange import (
    OI_STEP_MS,
    SETTLE_MS,
    FakeExchange,
    open_interest,
    settlement_rate,
)
from tests.evals.frames import BASE_MS, STEP_MS, make_frame

HISTORY = 300
OI_LIMIT = OrderFlowCalculator(15).oi_history_limit


def _at(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC)


def settlements(start_ms: int, count: int) -> pd.DataFrame:
    times = start_ms - start_ms % SETTLE_MS + SETTLE_MS * np.arange(count)
    return pd.DataFrame(
        {TIME: times.astype(np.int64), VALUE: [settlement_rate(int(t)) for t in times]}
    )


def snapshots(start_ms: int, count: int) -> pd.DataFrame:
    times = start_ms - start_ms % OI_STEP_MS + OI_STEP_MS * np.arange(count)
    return pd.DataFrame(
        {TIME: times.astype(np.int64), VALUE: [open_interest(int(t)) for t in times]}
    )


def _exchange(fake: FakeExchange) -> ExchangeClient:
    return cast("ExchangeClient", fake)


@pytest.fixture
def cache(tmp_path: Path) -> SeriesCache:
    return SeriesCache(tmp_path / "cache", "funding")


@pytest.fixture
def sampler(app_config: AppConfig) -> SignalSampler:
    return SignalSampler(
        MarketFeatureBuilder(app_config.risk), HISTORY, 41, OrderFlowCalculator(15)
    )


class TestSeriesCache:
    def test_missing_file_loads_empty(self, cache: SeriesCache) -> None:
        assert cache.load("NONE").empty

    def test_merge_dedupes_and_sorts(self, cache: SeriesCache) -> None:
        cache.merge("AAA", [30, 10], [3.0, 1.0])
        cache.merge("AAA", [10, 20], [9.0, 2.0])
        frame = cache.load("AAA")
        assert frame[TIME].tolist() == [10, 20, 30]
        assert frame[VALUE].tolist() == [9.0, 2.0, 3.0]

    def test_rejects_mismatched_lengths(self, cache: SeriesCache) -> None:
        with pytest.raises(ValueError, match="2 times but 1 values"):
            cache.merge("AAA", [1, 2], [1.0])


class TestFundingDownloader:
    async def test_pages_and_fills_the_range(self, cache: SeriesCache) -> None:
        fake = FakeExchange(BASE_MS)
        end = BASE_MS + 1500 * SETTLE_MS

        await FundingDownloader(_exchange(fake), cache).ensure_range(
            "AAA", BASE_MS, end
        )

        frame = cache.load("AAA")
        assert len(frame) == 1500
        assert frame[TIME].is_monotonic_increasing
        assert [c[2] for c in fake.funding_calls] == [1000, 1000]

    async def test_rerun_fetches_only_the_tail(self, cache: SeriesCache) -> None:
        fake = FakeExchange(BASE_MS)
        downloader = FundingDownloader(_exchange(fake), cache)
        await downloader.ensure_range("AAA", BASE_MS, BASE_MS + 10 * SETTLE_MS)
        fake.funding_calls.clear()

        await downloader.ensure_range("AAA", BASE_MS, BASE_MS + 20 * SETTLE_MS)

        assert len(cache.load("AAA")) == 20
        assert len(fake.funding_calls) == 1
        assert fake.funding_calls[0][0] > BASE_MS + 9 * SETTLE_MS

    async def test_fetches_a_head_gap_longer_than_a_settlement(
        self, cache: SeriesCache
    ) -> None:
        fake = FakeExchange(BASE_MS)
        downloader = FundingDownloader(_exchange(fake), cache)
        await downloader.ensure_range("AAA", BASE_MS, BASE_MS + 10 * SETTLE_MS)
        fake.funding_calls.clear()

        earlier = BASE_MS - 5 * SETTLE_MS
        await downloader.ensure_range("AAA", earlier, BASE_MS + 10 * SETTLE_MS)

        assert fake.funding_calls[0][0] == earlier
        assert len(cache.load("AAA")) == 15

    async def test_rejects_an_empty_range(self, cache: SeriesCache) -> None:
        with pytest.raises(ValueError, match="empty range"):
            await FundingDownloader(
                _exchange(FakeExchange(BASE_MS)), cache
            ).ensure_range("AAA", BASE_MS, BASE_MS)


class TestOiDownloader:
    async def test_pages_with_explicit_end_times(self, tmp_path: Path) -> None:
        end = BASE_MS + 1200 * OI_STEP_MS
        fake = FakeExchange(now_ms=end + 50 * OI_STEP_MS)
        cache = SeriesCache(tmp_path, "oi_15m")

        await OiDownloader(_exchange(fake), cache, "15m").ensure_range(
            "AAA", BASE_MS, end
        )

        frame = cache.load("AAA")
        # Rows stop at the requested end, not at the exchange's "now".
        assert len(frame) == 1200
        assert int(frame[TIME].iloc[-1]) < end
        assert all(call[1] is not None for call in fake.oi_calls)
        assert len(fake.oi_calls) == 3

    async def test_rerun_with_cache_covered_makes_no_request(
        self, tmp_path: Path
    ) -> None:
        end = BASE_MS + 100 * OI_STEP_MS
        fake = FakeExchange(now_ms=end)
        downloader = OiDownloader(
            _exchange(fake), SeriesCache(tmp_path, "oi_15m"), "15m"
        )
        await downloader.ensure_range("AAA", BASE_MS, end)
        fake.oi_calls.clear()

        await downloader.ensure_range("AAA", BASE_MS, end)

        assert fake.oi_calls == []


class TestSamplerFunding:
    def test_matches_live_zscore_without_look_ahead(
        self, sampler: SignalSampler
    ) -> None:
        frame = make_frame(HISTORY + 150, seed=2)
        funding = settlements(BASE_MS - 150 * SETTLE_MS, 200)

        samples = sampler.sample("AAA", frame, max_horizon=10, funding=funding)

        assert len(samples) > 1
        for row in samples.itertuples():
            close_ms = int(frame["close_time_ms"].iloc[int(row.idx)])
            settled = funding[funding[TIME] <= close_ms].tail(100)
            live = calculate_funding_zscore(
                [
                    FundingRateSchema(
                        symbol="AAA",
                        funding_rate=Decimal(str(r.value)),
                        funding_time=_at(int(r.time_ms)),
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

    def test_without_funding_there_is_no_funding_column(
        self, sampler: SignalSampler
    ) -> None:
        samples = sampler.sample("AAA", make_frame(HISTORY + 60), max_horizon=10)
        assert f"LONG_{FUNDING_SIGNAL}" not in samples
        assert "funding_z" not in samples


class TestSamplerOi:
    def test_matches_live_order_flow_on_full_history_bars(
        self, sampler: SignalSampler
    ) -> None:
        frame = make_frame(HISTORY + 300, seed=4)
        funding = settlements(BASE_MS - 150 * SETTLE_MS, 250)
        # OI starts mid-frame, so early bars lack the 97-row history live needs.
        oi_start = BASE_MS + (HISTORY + 20) * STEP_MS
        oi = snapshots(oi_start, 400)

        samples = sampler.sample("AAA", frame, 10, funding=funding, oi=oi)

        assert len(samples) > 1
        live = OrderFlowCalculator(15)
        for row in samples.itertuples():
            close_ms = int(frame["close_time_ms"].iloc[int(row.idx)])
            known = oi[oi[TIME] <= close_ms]
            assert len(known) >= OI_LIMIT
            flow = live.calculate(
                "AAA",
                [
                    FundingRateSchema(
                        symbol="AAA",
                        funding_rate=Decimal(str(r.value)),
                        funding_time=_at(int(r.time_ms)),
                    )
                    for r in funding[funding[TIME] <= close_ms].tail(100).itertuples()
                ],
                [
                    OpenInterestSchema(
                        symbol="AAA",
                        open_interest=Decimal(str(r.value)),
                        timestamp=_at(int(r.time_ms)),
                    )
                    for r in known.tail(OI_LIMIT).itertuples()
                ],
            )
            assert flow is not None
            assert row.oi_change_1h == float(flow.oi_change_1h_percent)
            assert row.LONG_oi_supports_direction == (flow.oi_change_1h_percent > 0)
            assert row.SHORT_oi_supports_direction == (flow.oi_change_1h_percent < 0)
            for side in ("LONG", "SHORT"):
                assert getattr(row, f"{side}_oi_funding_divergence") == (
                    flow.oi_funding_divergence_direction == side
                )

    def test_drops_bars_without_full_oi_history(self, sampler: SignalSampler) -> None:
        frame = make_frame(HISTORY + 300)
        funding = settlements(BASE_MS - 150 * SETTLE_MS, 250)
        oi_start = BASE_MS + (HISTORY + 20) * STEP_MS

        samples = sampler.sample(
            "AAA", frame, 10, funding=funding, oi=snapshots(oi_start, 400)
        )

        first_ok = oi_start + (OI_LIMIT - 1) * OI_STEP_MS
        closes = frame["close_time_ms"].iloc[samples["idx"]]
        assert (closes >= first_ok).all()
        for name in OI_SIGNALS:
            assert f"LONG_{name}" in samples

    def test_oi_requires_funding(self, sampler: SignalSampler) -> None:
        with pytest.raises(ValueError, match="need funding"):
            sampler.sample("AAA", make_frame(HISTORY + 60), 10, oi=snapshots(0, 5))
