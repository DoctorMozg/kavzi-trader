from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.config import AppConfig
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.evals.market_feature_builder import MarketFeatureBuilder
from kavzi_trader.evals.signal_bracket_schema import SignalBracketSchema
from kavzi_trader.evals.signal_edge_analyzer import SignalEdgeAnalyzer
from kavzi_trader.evals.signal_report_renderer import SignalReportRenderer
from kavzi_trader.evals.signal_sampler import CANDLE_SIGNALS, SIDES, SignalSampler
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from tests.evals.frames import make_frame

HISTORY = 300


def _candles(frame: pd.DataFrame) -> list[CandlestickSchema]:
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
        for r in frame.itertuples()
    ]


def _trend_frame(n: int) -> pd.DataFrame:
    """Close rises 1.0 per bar with a 0.2 range, so LONG always wins."""
    frame = make_frame(n)
    close = 100.0 + np.arange(n, dtype=np.float64)
    frame["open"] = close - 1.0
    frame["close"] = close
    frame["high"] = close + 0.1
    frame["low"] = close - 1.1
    return frame


def _samples(idx: list[int], fired: list[bool], scores: list[int]) -> pd.DataFrame:
    data: dict[str, object] = {"symbol": "AAA", "idx": idx, "atr": 1.0}
    for side in SIDES:
        for name in CANDLE_SIGNALS:
            data[f"{side}_{name}"] = fired
        data[f"{side}_score"] = scores
    return pd.DataFrame(data)


@pytest.fixture
def sampler(app_config: AppConfig) -> SignalSampler:
    return SignalSampler(MarketFeatureBuilder(app_config.risk), HISTORY, stride=37)


class TestSignalBracket:
    def test_parses_sl_tp_bars(self) -> None:
        bracket = SignalBracketSchema.parse("1.5:3:96")
        assert (bracket.sl_atr, bracket.tp_atr, bracket.horizon_bars) == (1.5, 3, 96)
        assert bracket.label == "1.5/3 ATR, 96 bars"

    @pytest.mark.parametrize("text", ["1.5:3", "a:3:96", "1:2:0", "-1:2:5"])
    def test_rejects_malformed(self, text: str) -> None:
        with pytest.raises(ValueError, match=r"bracket|greater|valid number"):
            SignalBracketSchema.parse(text)


class TestSignalSampler:
    def test_flags_match_live_calculators_on_candles(
        self, sampler: SignalSampler
    ) -> None:
        frame = make_frame(HISTORY + 120, seed=5)
        samples = sampler.sample("AAA", frame, max_horizon=10)
        live = ConfluenceCalculator()
        for row in samples.itertuples():
            window = frame.iloc[int(row.idx) - HISTORY + 1 : int(row.idx) + 1]
            candles = _candles(window)
            indicators = TechnicalIndicatorCalculator().calculate(candles)
            assert indicators is not None
            for side in SIDES:
                conf = live.evaluate(side, candles[-1], indicators, None)
                assert getattr(row, f"{side}_score") == conf.score
                for name in CANDLE_SIGNALS:
                    assert getattr(row, f"{side}_{name}") == getattr(conf, name)

    def test_samples_full_windows_and_leaves_the_horizon(
        self, sampler: SignalSampler
    ) -> None:
        frame = make_frame(HISTORY + 200)
        samples = sampler.sample("AAA", frame, max_horizon=50)

        idx = samples["idx"].tolist()
        assert idx[0] == HISTORY - 1
        assert set(np.diff(idx)) == {37}
        assert idx[-1] + 50 < len(frame)
        assert set(samples["regime"]) <= {"LOW", "NORMAL", "HIGH", "EXTREME"}

    def test_too_short_frame_gives_no_samples(self, sampler: SignalSampler) -> None:
        assert sampler.sample("AAA", make_frame(HISTORY), max_horizon=10).empty


class TestSignalEdgeAnalyzer:
    def test_measures_fired_and_unfired_r(self) -> None:
        frame = _trend_frame(100)
        samples = _samples([10, 20, 30, 40], [True, False, True, False], [0, 1, 4, 6])
        bracket = SignalBracketSchema(sl_atr=1.5, tp_atr=3.0, horizon_bars=10)

        result = SignalEdgeAnalyzer(stride=5, signals=CANDLE_SIGNALS).analyze(
            samples, {"AAA": frame}, bracket
        )

        assert result.samples == 4
        assert result.ci_widening == pytest.approx(2**0.5)
        assert result.label_shares == {"LONG": 1.0, "SHORT": 0.0, "NO_TRADE": 0.0}
        assert result.base["LONG"].mean_r == pytest.approx(2.0)
        assert result.base["SHORT"].mean_r == pytest.approx(-1.0)
        edge = next(
            e for e in result.signals if e.side == "LONG" and e.signal == "volume_spike"
        )
        assert edge.fired_share == 0.5
        assert (edge.fired.n, edge.fired.win_rate, edge.fired.ci95) == (2, 1.0, 0.0)
        top = [
            b for b in result.score_buckets if b.side == "SHORT" and b.bucket == "4+"
        ]
        assert top[0].stat.n == 2

    def test_empty_group_has_no_mean(self) -> None:
        samples = _samples([10, 20], [False, False], [0, 0])
        result = SignalEdgeAnalyzer(stride=5, signals=CANDLE_SIGNALS).analyze(
            samples,
            {"AAA": _trend_frame(50)},
            SignalBracketSchema(sl_atr=1, tp_atr=2, horizon_bars=5),
        )

        fired = result.signals[0].fired
        assert (fired.n, fired.mean_r, fired.ci95) == (0, None, None)


class TestSignalReportRenderer:
    def test_lists_only_signals_whose_interval_excludes_zero(self) -> None:
        samples = _samples([10, 20, 30, 40], [True, False, True, False], [0] * 4)
        frame = _trend_frame(100)
        result = SignalEdgeAnalyzer(stride=5, signals=CANDLE_SIGNALS).analyze(
            samples, {"AAA": frame}, SignalBracketSchema.parse("1.5:3:10")
        )
        renderer = SignalReportRenderer(stride=5, history=HISTORY, symbols=["AAA"])

        text = renderer.render([result])

        assert "LONG ema_alignment +2.000" in text
        assert "SHORT ema_alignment -1.000" in text
        assert "## 1.5/3 ATR, 10 bars" in text
        assert renderer.summary([result])[0].startswith(
            "1.5/3 ATR, 10 bars: 4 bars, LONG"
        )
