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
from kavzi_trader.order_flow.calculator import OrderFlowCalculator
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from tests.evals.frames import make_frame

HISTORY = 300
COMMISSION = 0.0005


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


def _path_frame(close: np.ndarray) -> pd.DataFrame:
    """Candles that move 1.0 per bar along ``close`` with 0.1 wicks."""
    frame = make_frame(len(close))
    open_ = np.concatenate(([close[0]], close[:-1]))
    frame["open"] = open_
    frame["close"] = close
    frame["high"] = np.maximum(open_, close) + 0.1
    frame["low"] = np.minimum(open_, close) - 0.1
    return frame


def _trend_frame(n: int) -> pd.DataFrame:
    """Close rises 1.0 per bar, so LONG always hits TP and SHORT its stop."""
    return _path_frame(100.0 + np.arange(n, dtype=np.float64))


def _vee_frame() -> pd.DataFrame:
    """Up for 50 bars, then down: LONG wins early, SHORT wins late."""
    up = 100.0 + np.arange(50, dtype=np.float64)
    return _path_frame(np.concatenate((up, up[-1] - np.arange(1, 51))))


def _analyzer() -> SignalEdgeAnalyzer:
    return SignalEdgeAnalyzer(
        stride=5, signals=CANDLE_SIGNALS, commission_rate=COMMISSION
    )


def _samples(idx: list[int], fired: list[bool], scores: list[int]) -> pd.DataFrame:
    data: dict[str, object] = {"symbol": "AAA", "idx": idx, "atr": 1.0}
    for side in SIDES:
        for name in CANDLE_SIGNALS:
            data[f"{side}_{name}"] = fired
        data[f"{side}_score"] = scores
    return pd.DataFrame(data)


@pytest.fixture
def sampler(app_config: AppConfig) -> SignalSampler:
    return SignalSampler(
        MarketFeatureBuilder(app_config.risk), HISTORY, 37, OrderFlowCalculator(15)
    )


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

        result = _analyzer().analyze(samples, {"AAA": frame}, bracket)

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
        # Same R either way: no lift, however certain.
        assert (edge.lift, edge.lift_ci95) == (0.0, 0.0)
        closes = np.array([110.0, 120.0, 130.0, 140.0])
        expected_fee = (2 * COMMISSION * closes / 1.5).mean()
        assert result.mean_fee_r == pytest.approx(expected_fee)
        top = [
            b for b in result.score_buckets if b.side == "SHORT" and b.bucket == "4+"
        ]
        assert top[0].stat.n == 2

    def test_empty_group_has_no_mean(self) -> None:
        samples = _samples([10, 20], [False, False], [0, 0])
        result = _analyzer().analyze(
            samples,
            {"AAA": _trend_frame(50)},
            SignalBracketSchema(sl_atr=1, tp_atr=2, horizon_bars=5),
        )

        fired = result.signals[0].fired
        assert (fired.n, fired.mean_r, fired.ci95) == (0, None, None)
        assert result.signals[0].lift is None


class TestSignalReportRenderer:
    def test_lists_signals_by_lift_not_by_drift(self) -> None:
        # Fired on the up leg only: LONG +2 vs -1, SHORT -1 vs +2.
        samples = _samples([10, 30, 60, 80], [True, True, False, False], [0] * 4)
        bracket = SignalBracketSchema.parse("1.5:3:10")
        lifted = _analyzer().analyze(samples, {"AAA": _vee_frame()}, bracket)
        drift = _analyzer().analyze(
            _samples([10, 20, 30, 40], [True, False, True, False], [0] * 4),
            {"AAA": _trend_frame(100)},
            bracket,
        )
        renderer = SignalReportRenderer(
            stride=5, history=HISTORY, symbols=["AAA"], interval="15m"
        )

        text = renderer.render([lifted])

        assert "LONG ema_alignment +3.000" in text
        assert "SHORT ema_alignment -3.000" in text
        assert "## 1.5/3 ATR, 10 bars" in text
        assert renderer.summary([drift])[0].endswith("no signal with lift")
