from datetime import datetime

import numpy as np
import pandas as pd

from kavzi_trader.api.binance.schemas.data_dicts import (
    FundingRateDict,
    LongShortRatioDict,
    OpenInterestHistDict,
)
from kavzi_trader.commons.clock import Clock
from kavzi_trader.evals.metrics_cache import GLOBAL_RATIO, OPEN_INTEREST
from kavzi_trader.evals.series_cache import TIME, VALUE

_MS_PER_MINUTE = 60_000


class HistoricalOrderFlowSource:
    """Serves archived funding and 5m metrics rows as Binance did at clock time.

    Each call returns the latest ``limit`` rows stamped at or before now; the
    time arguments are ignored, as the live fetcher never passes them.
    """

    def __init__(
        self,
        clock: Clock,
        funding: dict[str, pd.DataFrame],
        metrics: dict[str, pd.DataFrame],
    ) -> None:
        self._clock = clock
        self._funding = funding
        # The metrics dump carries open interest for years; the OI endpoint
        # keeps only 30 days.
        self._metrics = metrics

    async def get_funding_rate(
        self,
        symbol: str,
        limit: int = 100,
        start_time: int | datetime | None = None,  # noqa: ARG002
        end_time: int | datetime | None = None,  # noqa: ARG002
    ) -> list[FundingRateDict]:
        rows = self._known(self._funding, symbol, limit)
        return [
            FundingRateDict(symbol=symbol, fundingRate=str(v), fundingTime=int(t))
            for t, v in zip(rows[TIME], rows[VALUE], strict=True)
        ]

    async def get_open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,  # noqa: ARG002
        end_time: int | datetime | None = None,  # noqa: ARG002
    ) -> list[OpenInterestHistDict]:
        rows = self._known(self._metrics, symbol, limit, period)
        return [
            # The fetcher reads only sumOpenInterest; the cache has no USD value.
            OpenInterestHistDict(
                symbol=symbol,
                sumOpenInterest=str(v),
                sumOpenInterestValue="0",
                timestamp=int(t),
            )
            for t, v in zip(rows[TIME], rows[OPEN_INTEREST], strict=True)
        ]

    async def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,  # noqa: ARG002
        end_time: int | datetime | None = None,  # noqa: ARG002
    ) -> list[LongShortRatioDict]:
        rows = self._known(self._metrics, symbol, limit, period)
        return [
            LongShortRatioDict(
                symbol=symbol,
                longShortRatio=str(ratio),
                longAccount=str(ratio / (1 + ratio)),
                shortAccount=str(1 / (1 + ratio)),
                timestamp=int(t),
            )
            for t, ratio in zip(rows[TIME], rows[GLOBAL_RATIO], strict=True)
        ]

    def _known(
        self,
        frames: dict[str, pd.DataFrame],
        symbol: str,
        limit: int,
        period: str | None = None,
    ) -> pd.DataFrame:
        frame = frames.get(symbol)
        if frame is None or frame.empty:
            return pd.DataFrame(
                {TIME: [], VALUE: [], OPEN_INTEREST: [], GLOBAL_RATIO: []}
            )
        times = frame[TIME].to_numpy(dtype=np.int64)
        known = times <= self._clock.now_ms()
        if period is not None:
            known &= times % (_period_minutes(period) * _MS_PER_MINUTE) == 0
        return frame[known].tail(limit)


def _period_minutes(period: str) -> int:
    if not period.endswith("m") or not period[:-1].isdigit():
        msg = f"unsupported period {period!r}; expected minutes like '15m'"
        raise ValueError(msg)
    return int(period[:-1])
