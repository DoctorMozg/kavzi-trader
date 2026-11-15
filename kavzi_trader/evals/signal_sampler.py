import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import numpy as np
import pandas as pd

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.evals.market_feature_builder import REGIME_ORDER, MarketFeatureBuilder
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
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
        self, symbol: str, frame: pd.DataFrame, max_horizon: int
    ) -> pd.DataFrame:
        """One row per sampled bar; leaves ``max_horizon`` bars after the last one."""
        features = self._features.build(frame)
        idx = np.arange(self._history - 1, len(frame) - max_horizon - 1, self._stride)
        idx = idx[
            np.isfinite(features.atr[idx]) & np.isfinite(features.atr_zscore[idx])
        ]
        rows = [self._row(frame, int(i)) for i in idx]
        samples = pd.DataFrame(rows)
        if samples.empty:
            logger.warning("%s: no bars to sample in %d candles", symbol, len(frame))
            return samples
        samples.insert(0, "symbol", symbol)
        samples["atr"] = features.atr[idx]
        samples["regime"] = [REGIME_ORDER[c].value for c in features.regime_code[idx]]
        logger.info("%s: sampled %d bars", symbol, len(samples))
        return samples

    def _row(self, frame: pd.DataFrame, i: int) -> dict[str, int | bool]:
        window = frame.iloc[i - self._history + 1 : i + 1]
        close_time = datetime.fromtimestamp(
            int(window["close_time_ms"].iloc[-1]) / _MS_PER_S, UTC
        )
        indicators = self._indicators.calculate_frame(window, close_time)
        if indicators is None:
            msg = f"no indicators for bar {i}"
            raise ValueError(msg)
        candle = self._candle(window.iloc[-1], close_time)
        row: dict[str, int | bool] = {"idx": i}
        for side in SIDES:
            # Not the detected side: skips the live "score is 0" warning per bar.
            conf = self._confluence.evaluate(
                side, candle, indicators, None, is_detected_side=False
            )
            for name in CANDLE_SIGNALS:
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
