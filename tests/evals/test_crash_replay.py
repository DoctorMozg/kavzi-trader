import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.crash_replay import CrashReplay
from kavzi_trader.evals.replay_variant_schema import ReplayVariantSchema
from kavzi_trader.evals.vol_spike_halving import HOUR, HOUR_MS, PRICE, VolSpikeHalving

DAY_START_MS = 1_760_054_400_000  # 2025-10-10 00:00 UTC
MINUTE_MS = 60_000


def _day(low: np.ndarray, close: np.ndarray, mark_low: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time_ms": DAY_START_MS + np.arange(len(close)) * MINUTE_MS,
            "low": low,
            "close": close,
            "mark_low": mark_low,
        }
    )


@pytest.fixture
def wick_day() -> pd.DataFrame:
    """Flat at 100, one minute wicks to 50 on the last price only, ends at 90."""
    close = np.full(1440, 100.0)
    close[1260:] = 90.0
    low = close.copy()
    low[1260] = 50.0
    return _day(low, close, mark_low=close.copy())


class TestCrashReplay:
    def test_last_price_stop_sells_the_wick_and_mark_price_rides_it_out(
        self, wick_day: pd.DataFrame
    ) -> None:
        replay = CrashReplay(stop_pct=0.3, fee=0.0)
        book, prev = {"A": 0.5}, {"A": 100.0}

        live = replay.run(
            book,
            prev,
            {"A": wick_day},
            ReplayVariantSchema(name="live", trigger="contract"),
        )
        mark = replay.run(
            book,
            prev,
            {"A": wick_day},
            ReplayVariantSchema(name="mark", trigger="mark"),
        )
        at_stop = replay.run(
            book, prev, {"A": wick_day},
            ReplayVariantSchema(name="at stop", trigger="contract", fill="stop"),
        )  # fmt: skip

        assert live.end_return == pytest.approx(0.5 * -0.5)
        assert [(s.symbol, s.minute) for s in live.stops] == [("A", "21:00")]
        assert at_stop.end_return == pytest.approx(0.5 * -0.3)
        assert mark.stops == []
        assert mark.end_return == pytest.approx(0.5 * -0.1)
        assert mark.worst_return == pytest.approx(0.5 * -0.5)
        assert mark.worst_minute == "21:00"

    def test_halving_before_the_drop_halves_the_loss_and_pays_both_legs(
        self, wick_day: pd.DataFrame
    ) -> None:
        replay = CrashReplay(stop_pct=0.3, fee=0.001)
        variant = ReplayVariantSchema(
            name="halved",
            trigger="mark",
            halve_from_ms={"A": DAY_START_MS + 20 * HOUR_MS},
        )

        result = replay.run({"A": 1.0}, {"A": 100.0}, {"A": wick_day}, variant)

        assert result.end_return == pytest.approx(0.5 * -0.1 - 2 * 0.001 * 0.5)


@pytest.fixture
def minutes() -> pd.DataFrame:
    """40 quiet days of 1m closes, then one hour of large moves at 14:00."""
    rng = np.random.default_rng(5)
    n = 41 * 1440
    log_ret = rng.normal(0, 0.0005, n)
    spike_start = 40 * 1440 + 14 * 60
    # Calmer than the history before the spike, so 14:00 is that day's first.
    log_ret[40 * 1440 : spike_start] = rng.normal(0, 0.0001, 14 * 60)
    log_ret[spike_start : spike_start + 60] = rng.normal(0, 0.01, 60)
    return pd.DataFrame(
        {
            "open_time_ms": DAY_START_MS + np.arange(n) * MINUTE_MS,
            "close": 100 * np.exp(np.cumsum(log_ret)),
        }
    )


class TestVolSpikeHalving:
    def test_fires_at_the_spike_hour_with_its_last_close(
        self, minutes: pd.DataFrame
    ) -> None:
        fired = VolSpikeHalving().triggers(minutes)

        # A p99 threshold is crossed by chance in ~1% of quiet hours as well.
        spike_day = pd.Timestamp("2025-11-19")
        assert fired.index.is_unique
        assert fired.index.min() >= pd.Timestamp("2025-11-09")
        assert fired.loc[spike_day, HOUR] == spike_day + pd.Timedelta(hours=14)
        assert (
            fired.loc[spike_day, PRICE]
            == minutes["close"].iloc[40 * 1440 + 15 * 60 - 1]
        )

    def test_adjustment_forgoes_half_the_move_after_the_spike(self) -> None:
        days = pd.DatetimeIndex(["2025-11-18", "2025-11-19"])
        closes = pd.DataFrame({"A": [100.0, 80.0]}, index=days)
        held = pd.DataFrame({"A": [0.0, 0.4]}, index=days)
        fired = {"A": pd.DataFrame({HOUR: [days[1]], PRICE: [90.0]}, index=[days[1]])}

        change = VolSpikeHalving().adjustments(held, closes, fired, fee=0.001)

        # Half of 0.4 avoids the 90 -> 80 leg (10% of the 100 previous close).
        assert change.loc[days[1]] == pytest.approx(
            0.5 * 0.4 * 0.1 - 2 * 0.5 * 0.4 * 0.001
        )
        assert change.loc[days[0]] == 0
