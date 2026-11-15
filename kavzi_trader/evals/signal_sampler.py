import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import numpy as np
import pandas as pd

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.evals.market_feature_builder import REGIME_ORDER, MarketFeatureBuilder
from kavzi_trader.evals.sample_window_schema import SampleWindowSchema
from kavzi_trader.evals.series_cache import TIME, VALUE
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.orchestrator.providers.live_order_flow_fetcher import (
    FUNDING_HISTORY_LIMIT,
)
from kavzi_trader.order_flow.calculator import OrderFlowCalculator
from kavzi_trader.order_flow.funding import calculate_funding_zscore
from kavzi_trader.order_flow.schemas import (
    FundingRateSchema,
    OpenInterestSchema,
    OrderFlowSchema,
)
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
OI_SIGNALS = ("oi_supports_direction", "oi_funding_divergence")
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
        order_flow: OrderFlowCalculator,
        window: SampleWindowSchema | None = None,
    ) -> None:
        if history < 1 or stride < 1:
            msg = f"history and stride must be >= 1, got {history}, {stride}"
            raise ValueError(msg)
        self._features = features
        self._history = history
        self._stride = stride
        self._indicators = TechnicalIndicatorCalculator()
        self._confluence = ConfluenceCalculator()
        self._order_flow = order_flow
        self._window = window or SampleWindowSchema()

    def sample(
        self,
        symbol: str,
        frame: pd.DataFrame,
        max_horizon: int,
        funding: pd.DataFrame | None = None,
        oi: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """One row per sampled bar; leaves ``max_horizon`` bars after the last one.

        With ``funding`` settlements, rows also carry the funding signal. Adding
        ``oi`` snapshots adds the OI signals and keeps only bars with a full OI
        history, since Binance serves only about the last 30 days.
        """
        if oi is not None and funding is None:
            msg = "OI signals need funding settlements too"
            raise ValueError(msg)
        features = self._features.build(frame)
        idx = np.arange(self._history - 1, len(frame) - max_horizon - 1, self._stride)
        close_ms = frame["close_time_ms"].to_numpy(dtype=np.int64)
        idx = idx[
            np.isfinite(features.atr[idx])
            & np.isfinite(features.atr_zscore[idx])
            & self._window.contains(close_ms[idx])
        ]
        lookup = (
            None
            if funding is None
            else _OrderFlowLookup(symbol, funding, oi, self._order_flow)
        )
        if lookup is not None and oi is not None:
            idx = idx[lookup.has_full_oi(close_ms[idx])]
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
        self, frame: pd.DataFrame, i: int, lookup: _OrderFlowLookup | None
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
        if lookup is not None:
            order_flow = lookup.at(int(window["close_time_ms"].iloc[-1]), close_time)
            row["funding_z"] = (
                np.nan if order_flow is None else float(order_flow.funding_zscore)
            )
            names = (*CANDLE_SIGNALS, FUNDING_SIGNAL)
            if lookup.with_oi:
                row["oi_change_1h"] = (
                    np.nan
                    if order_flow is None
                    else float(order_flow.oi_change_1h_percent)
                )
                names = (*names, *OI_SIGNALS)
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


class _OrderFlowLookup:
    """Live order flow as of any bar, from cached funding and OI history.

    Funding alone: the z-score only changes at a settlement, so it is computed
    once per settlement over the FUNDING_HISTORY_LIMIT latest, as the live
    fetcher does. With OI, each bar goes through the live OrderFlowCalculator
    with the funding and OI rows a live fetch would have returned at its close.
    """

    def __init__(
        self,
        symbol: str,
        funding: pd.DataFrame,
        oi: pd.DataFrame | None,
        calculator: OrderFlowCalculator,
    ) -> None:
        self._symbol = symbol
        self._calculator = calculator
        self._funding_times = funding[TIME].to_numpy(dtype=np.int64)
        self._rates = [
            FundingRateSchema(
                symbol=symbol,
                funding_rate=Decimal(str(rate)),
                funding_time=datetime.fromtimestamp(ms / _MS_PER_S, UTC),
            )
            for ms, rate in zip(self._funding_times, funding[VALUE], strict=True)
        ]
        self._analyses = [
            calculate_funding_zscore(self._settled(k)) for k in range(len(self._rates))
        ]
        self._oi_times = (
            np.empty(0, np.int64) if oi is None else oi[TIME].to_numpy(dtype=np.int64)
        )
        self._oi = (
            None
            if oi is None
            else [
                OpenInterestSchema(
                    symbol=symbol,
                    open_interest=Decimal(str(value)),
                    timestamp=datetime.fromtimestamp(ms / _MS_PER_S, UTC),
                )
                for ms, value in zip(self._oi_times, oi[VALUE], strict=True)
            ]
        )

    @property
    def with_oi(self) -> bool:
        return self._oi is not None

    def has_full_oi(self, close_ms: np.ndarray) -> np.ndarray:
        """Bars whose close has the full OI history a live fetch requests."""
        known = np.searchsorted(self._oi_times, close_ms, side="right")
        return known >= self._calculator.oi_history_limit

    def at(self, close_ms: int, close_time: datetime) -> OrderFlowSchema | None:
        """Order flow known at ``close_ms``; None before two funding settlements."""
        k = int(np.searchsorted(self._funding_times, close_ms, side="right")) - 1
        if k < 0:
            return None
        if self._oi is not None:
            known = int(np.searchsorted(self._oi_times, close_ms, side="right"))
            history = self._oi[
                max(0, known - self._calculator.oi_history_limit) : known
            ]
            return self._calculator.calculate(self._symbol, self._settled(k), history)
        analysis = self._analyses[k]
        if analysis is None:
            return None
        # Without OI history a zero change keeps both OI signals off.
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

    def _settled(self, k: int) -> list[FundingRateSchema]:
        return self._rates[max(0, k + 1 - FUNDING_HISTORY_LIMIT) : k + 1]
