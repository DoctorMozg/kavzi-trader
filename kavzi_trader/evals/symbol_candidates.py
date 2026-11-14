import logging
from typing import Annotated

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.bracket_policy import BracketPolicy
from kavzi_trader.evals.market_feature_builder import MarketFeatureBuilder
from kavzi_trader.evals.market_features_schema import MarketFeaturesSchema
from kavzi_trader.evals.triple_barrier import (
    LabeledBarriersSchema,
    TripleBarrierLabeler,
)

logger = logging.getLogger(__name__)


class SymbolCandidatesSchema(BaseModel):
    """Every labeled decision time of one symbol, aligned with ``entry_idx``."""

    entry_idx: Annotated[NDArray[np.int64], Field(...)]
    sl_distance: Annotated[NDArray[np.float64], Field(...)]
    tp_distance: Annotated[NDArray[np.float64], Field(...)]
    features: Annotated[MarketFeaturesSchema, Field(...)]
    barriers: Annotated[LabeledBarriersSchema, Field(...)]
    excluded_warmup_or_gap: Annotated[int, Field(..., ge=0)]
    excluded_geometry_rejected: Annotated[int, Field(..., ge=0)]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class SymbolCandidateFinder:
    """Finds and labels the decision times that satisfy warm-up and horizon rules."""

    def __init__(
        self,
        features: MarketFeatureBuilder,
        brackets: BracketPolicy,
        labeler: TripleBarrierLabeler,
        history_candles: int,
        horizon_bars: int,
        interval_ms: int,
    ) -> None:
        self._features = features
        self._brackets = brackets
        self._labeler = labeler
        self._history = history_candles
        self._horizon = horizon_bars
        self._interval_ms = interval_ms

    def find(self, frame: pd.DataFrame, window_start_ms: int) -> SymbolCandidatesSchema:
        """Label candidates whose candle opens at or after ``window_start_ms``.

        Each needs the full live candle window before it and a full vertical
        barrier after it, with no missing candles anywhere in between.
        """
        high = frame["high"].to_numpy(dtype=np.float64)
        low = frame["low"].to_numpy(dtype=np.float64)
        close = frame["close"].to_numpy(dtype=np.float64)
        open_ms = frame["open_time_ms"].to_numpy(dtype=np.int64)
        features = self._features.build(frame)

        n = len(close)
        index = np.arange(n)
        segment = np.concatenate(
            ([0], np.cumsum(np.diff(open_ms) != self._interval_ms))
        )
        first = index - (self._history - 1)
        last = index + self._horizon
        in_range = (first >= 0) & (last < n) & (open_ms >= window_start_ms)
        contiguous = np.zeros(n, dtype=bool)
        contiguous[in_range] = segment[first[in_range]] == segment[last[in_range]]
        warm = contiguous & np.isfinite(features.atr)

        distances = self._brackets.distances(features.regime_code, features.atr, close)
        usable = warm & distances.valid
        entry_idx = index[usable].astype(np.int64)
        sl = distances.sl_distance[usable]
        tp = distances.tp_distance[usable]
        barriers = self._labeler.label(high, low, close, entry_idx, sl, tp)
        in_window = int(((open_ms >= window_start_ms) & (last < n)).sum())
        logger.info(
            "Candidates: %d labeled, %d lacking warm-up/gap-free history, "
            "%d geometry-rejected",
            len(entry_idx),
            in_window - int(warm.sum()),
            int(warm.sum() - usable.sum()),
        )
        return SymbolCandidatesSchema(
            entry_idx=entry_idx,
            sl_distance=sl,
            tp_distance=tp,
            features=features,
            barriers=barriers,
            excluded_warmup_or_gap=in_window - int(warm.sum()),
            excluded_geometry_rejected=int(warm.sum() - usable.sum()),
        )
