import pandas as pd
import pytest

from kavzi_trader.evals.timing_halving import TimingHalving
from kavzi_trader.evals.vol_spike_halving import HOUR, PRICE, VolSpikeHalving

FEE = 0.001
DAY = pd.Timestamp("2027-01-02")


def _trigger(hour: int, price: float) -> pd.DataFrame:
    start = DAY + pd.Timedelta(hours=hour)
    return pd.DataFrame({HOUR: [start], PRICE: [price]}, index=[DAY])


def _six_hour(
    weights: list[float], closes: list[float]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Checks at DAY 00:00 (weight before the spike) through DAY + 1 00:00."""
    checks = pd.date_range(DAY, periods=5, freq="6h")
    held = pd.DataFrame({"S": weights}, index=checks)
    bars = pd.DataFrame({"S": closes}, index=checks - pd.Timedelta(hours=6))
    return held, bars


class TestTimingHalving:
    def test_a_daily_book_matches_the_daily_halving_model(self) -> None:
        days = pd.date_range(DAY - pd.Timedelta(days=1), periods=3, freq="D")
        held = pd.DataFrame({"S": [0.2, 0.2, 0.2]}, index=days)
        closes = pd.DataFrame({"S": [100.0, 110.0, 99.0]}, index=days)
        triggers = {"S": _trigger(10, 105.0)}

        daily = VolSpikeHalving(scale=0.5).adjustments(held, closes, triggers, FEE)
        # Day x's close is the 24h bar opening at x, checked at x + 1 00:00.
        timed = TimingHalving(0.5, FEE).adjustments(held, closes, 24, triggers)

        assert timed[DAY] == pytest.approx(daily[DAY])
        assert timed[DAY] != 0

    def test_a_6h_exit_after_the_spike_ends_the_forgone_move(self) -> None:
        # Spike 10:00-11:00 at 102; exit at the 12:00 check (close 101).
        held, bars = _six_hour([0.2, 0.2, 0.0, 0.0, 0.0], [100, 99, 101, 90, 80])

        change = TimingHalving(0.5, FEE).adjustments(
            held, bars, 6, {"S": _trigger(10, 102.0)}
        )

        forgone = 0.5 * 0.2 * (101 - 102) / 100
        # The halving sells 0.1 early, so the exit sells only the other 0.1.
        extra_fee = FEE * ((0.1 + 0.1) - 0.2)
        assert change[DAY] == pytest.approx(-forgone - extra_fee)

    def test_an_entry_after_the_spike_is_halved_until_the_next_day(self) -> None:
        # Flat at the spike; the 12:00 check enters 0.2, kept to the next day.
        held, bars = _six_hour([0.0, 0.0, 0.2, 0.2, 0.2], [100, 99, 101, 104, 103])

        change = TimingHalving(0.5, FEE).adjustments(
            held, bars, 6, {"S": _trigger(10, 102.0)}
        )

        forgone = 0.5 * 0.2 * ((104 - 101) + (103 - 104)) / 100
        extra_fee = FEE * ((0.1 + 0.1) - 0.2)
        assert change[DAY] == pytest.approx(-forgone - extra_fee)

    def test_rejects_a_scale_outside_zero_to_one(self) -> None:
        with pytest.raises(ValueError, match="scale"):
            TimingHalving(1.5, FEE)
