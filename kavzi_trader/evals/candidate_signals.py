from decimal import Decimal

import numpy as np
import pandas as pd

from kavzi_trader.indicators.htf import htf_trend_from_closes

CANDIDATE_SIGNALS = ("taker_flow", "htf_trend", "btc_lead")
LEADER_SYMBOL = "BTCUSDT"
# Flow and lead windows, in bars (one hour at 15m).
_LOOKBACK_BARS = 4
# Fixed before looking at outcomes: the top or bottom third of the trailing
# window counts as a signal, so each side fires on about a third of bars.
_UPPER_RANK = 2 / 3
_LOWER_RANK = 1 / 3
_MS_PER_HOUR = 3_600_000


class CandidateSignals:
    """Signals the live confluence score does not use yet, for edge testing.

    taker_flow: taker-buy share of volume over the last 4 bars, ranked within
    the trailing history window. htf_trend: the live 1h trend agrees with the
    side (15m candles only). btc_lead: BTC's return over the last 4 bars,
    ranked the same way, for every other symbol.
    """

    def __init__(self, history: int, leader: pd.DataFrame | None, *, htf: bool) -> None:
        self._history = history
        self._htf = htf
        self._leader_rank = None if leader is None else self._leader_ranks(leader)

    def add(
        self, symbol: str, frame: pd.DataFrame, samples: pd.DataFrame
    ) -> pd.DataFrame:
        """``samples`` plus LONG_/SHORT_ columns for each candidate signal."""
        if samples.empty:
            return samples
        idx = samples["idx"].to_numpy(dtype=np.int64)
        out = samples.copy()
        flow_rank = self._rank(self._taker_share(frame)).to_numpy()[idx]
        self._put(out, "taker_flow", flow_rank)
        if self._htf:
            direction = np.array([self._htf_direction(frame, int(i)) for i in idx])
            out["LONG_htf_trend"] = direction == "LONG"
            out["SHORT_htf_trend"] = direction == "SHORT"
        if self._leader_rank is not None:
            lead = np.full(len(idx), np.nan)
            if symbol != LEADER_SYMBOL:
                close_ms = frame["close_time_ms"].to_numpy(dtype=np.int64)[idx]
                lead = self._leader_rank.reindex(close_ms).to_numpy()
            self._put(out, "btc_lead", lead)
        return out

    @staticmethod
    def _put(out: pd.DataFrame, name: str, rank: np.ndarray) -> None:
        # NaN ranks (warm-up, missing leader bars) compare False on both sides.
        out[f"LONG_{name}"] = rank >= _UPPER_RANK
        out[f"SHORT_{name}"] = rank <= _LOWER_RANK

    def _rank(self, series: pd.Series) -> pd.Series:
        return series.rolling(self._history).rank(pct=True)

    @staticmethod
    def _taker_share(frame: pd.DataFrame) -> pd.Series:
        buys = frame["taker_buy_base_volume"].rolling(_LOOKBACK_BARS).sum()
        volume = frame["volume"].rolling(_LOOKBACK_BARS).sum()
        return buys / volume.where(volume > 0)

    def _leader_ranks(self, leader: pd.DataFrame) -> pd.Series:
        close = leader["close"]
        ranks = self._rank(np.log(close / close.shift(_LOOKBACK_BARS)))
        return pd.Series(
            ranks.to_numpy(), index=leader["close_time_ms"].to_numpy(dtype=np.int64)
        )

    def _htf_direction(self, frame: pd.DataFrame, i: int) -> str:
        window = frame.iloc[i - self._history + 1 : i + 1]
        # Same bucketing as the live aggregate_1h_closes: last close per UTC hour.
        hourly = window.groupby(window["open_time_ms"] // _MS_PER_HOUR)["close"].last()
        closes = [Decimal(str(c)) for c in hourly]
        return htf_trend_from_closes(closes).direction
