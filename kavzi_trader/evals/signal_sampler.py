import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import numpy as np
import pandas as pd

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.evals.market_feature_builder import REGIME_ORDER, MarketFeatureBuilder
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.orchestrator.providers.live_order_flow_fetcher import (
    FUNDING_HISTORY_LIMIT,
)
from kavzi_trader.order_flow.funding import calculate_funding_zscore
from kavzi_trader.order_flow.schemas import FundingRateSchema, OrderFlowSchema
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator

logger = logging.getLogger(__name__)

SIDES: tuple[Literal["LONG", "SHORT"], ...] = ("LONG", "SHORT")
CANDLE_SIGNALS = (
    "ema_alignment",
    "rsi_favorable",
    "volume_above_average",
    "price_at_bollinger",
    "volume_spike",
)
FUNDING_SIGNAL = "funding_favorable"
_MS_PER_S = 1000


class SignalSampler:
    """Live confluence signals on every ``stride``-th bar of a cached candle frame.

    Indicators come from the live calculator over the trailing ``history`` bars,
    the window the live bot keeps, and flags from the live ConfluenceCalculator.
    """

    def __init__(
        self,
        features: MarketFeatureBuilder,
        history: int,
        stride: int,
    ) -> None:
        if history < 1 or stride < 1:
            msg = f"history and stride must be >= 1, got {history}, {stride}"
            raise ValueError(msg)
        self._features = features
        self._history = history
        self._stride = stride
        self._indicators = TechnicalIndicatorCalculator()
        self._confluence = ConfluenceCalculator()

    def sample(
        self,
        symbol: str,
        frame: pd.DataFrame,
        max_horizon: int,
        funding: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """One row per sampled bar; leaves ``max_horizon`` bars after the last one.

        With ``funding`` settlements, rows also carry the funding signal.
        """
        features = self._features.build(frame)
        idx = np.arange(self._history - 1, len(frame) - max_horizon - 1, self._stride)
        idx = idx[
            np.isfinite(features.atr[idx]) & np.isfinite(features.atr_zscore[idx])
        ]
        lookup = None if funding is None else _FundingLookup(symbol, funding)
        rows = [self._row(frame, int(i), lookup) for i in idx]
        samples = pd.DataFrame(rows)
        if samples.empty:
            logger.warning("%s: no bars to sample in %d candles", symbol, len(frame))
            return samples
        samples.insert(0, "symbol", symbol)
        samples["atr"] = features.atr[idx]
        samples["regime"] = [REGIME_ORDER[c].value for c in features.regime_code[idx]]
        logger.info("%s: sampled %d bars", symbol, len(samples))
        return samples

    def _row(
        self, frame: pd.DataFrame, i: int, funding: _FundingLookup | None
    ) -> dict[str, int | bool | float]:
        window = frame.iloc[i - self._history + 1 : i + 1]
        close_time = datetime.fromtimestamp(
            int(window["close_time_ms"].iloc[-1]) / _MS_PER_S, UTC
        )
        indicators = self._indicators.calculate_frame(window, close_time)
        if indicators is None:
            msg = f"no indicators for bar {i}"
            raise ValueError(msg)
        candle = self._candle(window.iloc[-1], close_time)
        order_flow = None
        row: dict[str, int | bool | float] = {"idx": i}
        names: tuple[str, ...] = CANDLE_SIGNALS
        if funding is not None:
            order_flow = funding.at(int(window["close_time_ms"].iloc[-1]), close_time)
            row["funding_z"] = (
                np.nan if order_flow is None else float(order_flow.funding_zscore)
            )
            names = (*CANDLE_SIGNALS, FUNDING_SIGNAL)
        for side in SIDES:
            # Not the detected side: skips the live "score is 0" warning per bar.
            conf = self._confluence.evaluate(
                side, candle, indicators, order_flow, is_detected_side=False
            )
            for name in names:
                row[f"{side}_{name}"] = bool(getattr(conf, name))
            row[f"{side}_score"] = conf.score
        return row

    @staticmethod
    def _candle(bar: pd.Series, close_time: datetime) -> CandlestickSchema:
        def dec(column: str) -> Decimal:
            return Decimal(str(bar[column]))

        return CandlestickSchema.model_validate(
            {
                "open_time": datetime.fromtimestamp(
                    int(bar["open_time_ms"]) / _MS_PER_S, UTC
                ),
                "close_time": close_time,
                "open_price": dec("open"),
                "high_price": dec("high"),
                "low_price": dec("low"),
                "close_price": dec("close"),
                "volume": dec("volume"),
                "quote_volume": dec("quote_volume"),
                "trades_count": int(bar["trades_count"]),
                "taker_buy_base_volume": dec("taker_buy_base_volume"),
                "taker_buy_quote_volume": dec("taker_buy_quote_volume"),
            }
        )


class _FundingLookup:
    """Live funding z-score as of any bar, from cached settlements.

    The z-score only changes at a settlement, so it is computed once per
    settlement over the FUNDING_HISTORY_LIMIT latest, as the live fetcher does.
    """

    def __init__(self, symbol: str, funding: pd.DataFrame) -> None:
        self._times = funding["funding_time_ms"].to_numpy(dtype=np.int64)
        rates = [
            FundingRateSchema(
                symbol=symbol,
                funding_rate=Decimal(str(rate)),
                funding_time=datetime.fromtimestamp(ms / _MS_PER_S, UTC),
            )
            for ms, rate in zip(self._times, funding["funding_rate"], strict=True)
        ]
        self._symbol = symbol
        self._analyses = [
            calculate_funding_zscore(
                rates[max(0, k + 1 - FUNDING_HISTORY_LIMIT) : k + 1]
            )
            for k in range(len(rates))
        ]

    def at(self, close_ms: int, close_time: datetime) -> OrderFlowSchema | None:
        """Order flow with the latest settled funding; None before two settlements."""
        k = int(np.searchsorted(self._times, close_ms, side="right")) - 1
        analysis = self._analyses[k] if k >= 0 else None
        if analysis is None:
            return None
        # OI history is not backtestable; a zero change keeps both OI signals off.
        return OrderFlowSchema(
            symbol=self._symbol,
            timestamp=close_time,
            funding_rate=analysis.funding_rate,
            funding_zscore=analysis.funding_zscore,
            next_funding_time=analysis.next_funding_time,
            open_interest=Decimal(0),
            oi_change_1h_percent=Decimal(0),
            oi_change_24h_percent=None,
        )
