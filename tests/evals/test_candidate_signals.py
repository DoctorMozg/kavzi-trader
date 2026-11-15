from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.evals.candidate_signals import LEADER_SYMBOL, CandidateSignals
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.indicators.htf import compute_htf_trend
from tests.evals.frames import make_frame

HISTORY = 500


def _samples(idx: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"symbol": "ETHUSDT", "idx": idx})


def _candles(window: pd.DataFrame) -> list[CandlestickSchema]:
    def at(ms: int) -> datetime:
        return datetime.fromtimestamp(ms / 1000, UTC)

    return [
        CandlestickSchema(
            open_time=at(int(r.open_time_ms)),
            open_price=Decimal(str(r.open)),
            high_price=Decimal(str(r.high)),
            low_price=Decimal(str(r.low)),
            close_price=Decimal(str(r.close)),
            volume=Decimal(str(r.volume)),
            close_time=at(int(r.close_time_ms)),
            quote_volume=Decimal(str(r.quote_volume)),
            trades_count=int(r.trades_count),
            taker_buy_base_volume=Decimal(str(r.taker_buy_base_volume)),
            taker_buy_quote_volume=Decimal(str(r.taker_buy_quote_volume)),
        )
        for r in window.itertuples()
    ]


def _with_taker_share(frame: pd.DataFrame, share: np.ndarray) -> pd.DataFrame:
    frame = frame.copy()
    frame["taker_buy_base_volume"] = frame["volume"] * share
    return frame


class TestTakerFlow:
    def test_heavy_buying_fires_long_and_heavy_selling_short(self) -> None:
        n = HISTORY + 20
        share = np.random.default_rng(1).uniform(0.4, 0.6, n)
        share[HISTORY : HISTORY + 4] = 0.9
        share[HISTORY + 10 : HISTORY + 14] = 0.1
        frame = _with_taker_share(make_frame(n), share)
        signals = CandidateSignals(HISTORY, None, htf=False)

        out = signals.add("ETHUSDT", frame, _samples([HISTORY + 3, HISTORY + 13]))

        assert out["LONG_taker_flow"].tolist() == [True, False]
        assert out["SHORT_taker_flow"].tolist() == [False, True]
        assert "LONG_htf_trend" not in out
        assert "LONG_btc_lead" not in out

    def test_warm_up_bars_never_fire(self) -> None:
        frame = make_frame(HISTORY + 20)
        out = CandidateSignals(HISTORY, None, htf=False).add(
            "ETHUSDT", frame, _samples([10, 100])
        )
        assert not out["LONG_taker_flow"].any()
        assert not out["SHORT_taker_flow"].any()


class TestHtfTrend:
    def test_matches_live_trend_from_candles(self) -> None:
        frame = make_frame(HISTORY + 200, seed=7, drift_vol=0.004)
        idx = list(range(HISTORY - 1, HISTORY + 200, 40))

        out = CandidateSignals(HISTORY, None, htf=True).add(
            "ETHUSDT", frame, _samples(idx)
        )

        for i, long, short in zip(
            idx, out["LONG_htf_trend"], out["SHORT_htf_trend"], strict=True
        ):
            live = compute_htf_trend(_candles(frame.iloc[i - HISTORY + 1 : i + 1]))
            assert long == (live.direction == "LONG")
            assert short == (live.direction == "SHORT")


class TestRsiExhausted:
    def test_fires_when_live_rsi_is_beyond_the_band_two_bars_running(self) -> None:
        frame = make_frame(HISTORY + 120, seed=4)
        rally = np.exp(0.004 * np.arange(60))
        for column in ("open", "high", "low", "close"):
            frame.loc[HISTORY : HISTORY + 59, column] *= rally
            frame.loc[HISTORY + 60 :, column] *= rally[-1]
        idx = list(range(HISTORY - 1, HISTORY + 119, 3))

        out = CandidateSignals(HISTORY, None, htf=False).add(
            "ETHUSDT", frame, _samples(idx)
        )

        def live_rsi(i: int) -> Decimal | None:
            window = frame.iloc[max(i - HISTORY + 1, 0) : i + 1]
            indicators = TechnicalIndicatorCalculator().calculate(_candles(window))
            assert indicators is not None
            return indicators.rsi_14

        for i, long, short in zip(
            idx, out["LONG_rsi_exhausted"], out["SHORT_rsi_exhausted"], strict=True
        ):
            pair = [live_rsi(i - 1), live_rsi(i)]
            assert long == all(r is not None and r > 70 for r in pair)
            assert short == all(r is not None and r < 30 for r in pair)
        assert out["LONG_rsi_exhausted"].any()


class TestBtcLead:
    def _leader(self, n: int) -> pd.DataFrame:
        leader = make_frame(n, seed=3)
        leader.loc[HISTORY : HISTORY + 3, "close"] *= 1.05
        return leader

    def test_leader_jump_fires_long_on_other_symbols(self) -> None:
        n = HISTORY + 20
        frame = make_frame(n, seed=9)
        signals = CandidateSignals(HISTORY, self._leader(n), htf=False)

        out = signals.add("ETHUSDT", frame, _samples([HISTORY + 3]))

        assert out["LONG_btc_lead"].tolist() == [True]
        assert out["SHORT_btc_lead"].tolist() == [False]

    def test_never_fires_on_the_leader_or_unmatched_bars(self) -> None:
        n = HISTORY + 20
        signals = CandidateSignals(HISTORY, self._leader(n), htf=False)
        shifted = make_frame(n, start_ms=10**12)

        on_leader = signals.add(LEADER_SYMBOL, make_frame(n), _samples([HISTORY + 3]))
        unmatched = signals.add("ETHUSDT", shifted, _samples([HISTORY + 3]))

        for out in (on_leader, unmatched):
            assert not out["LONG_btc_lead"].any()
            assert not out["SHORT_btc_lead"].any()

    def test_empty_samples_pass_through(self) -> None:
        empty = pd.DataFrame()
        assert (
            CandidateSignals(HISTORY, None, htf=True)
            .add("ETHUSDT", make_frame(10), empty)
            .empty
        )
