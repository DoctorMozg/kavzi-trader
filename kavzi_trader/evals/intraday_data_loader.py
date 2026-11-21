import logging

import numpy as np
import pandas as pd

from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.bar_quality_schema import BarQualitySchema
from kavzi_trader.evals.intraday_data_schema import IntradayDataSchema
from kavzi_trader.evals.timing_arm_schema import HOURS_PER_DAY

logger = logging.getLogger(__name__)

MS_PER_HOUR = 3_600_000
# Relative difference above which a 1h-derived day close counts as disagreeing.
DAY_END_TOLERANCE = 1e-6
_EPOCH = pd.Timestamp("1970-01-01")


class IntradayDataLoader:
    """Builds bars of any hour length from archived 1h klines, for every symbol."""

    def __init__(self, archive: ArchiveSeries) -> None:
        self._archive = archive

    def load(
        self, symbols: list[str], daily: pd.DataFrame, hours: list[int]
    ) -> dict[int, IntradayDataSchema]:
        hourly = {s: self._archive.hourly_closes(s) for s in symbols}
        return {h: self.build(hourly, daily, h) for h in hours}

    def build(
        self, hourly: dict[str, pd.DataFrame], daily: pd.DataFrame, hours: int
    ) -> IntradayDataSchema:
        """Bars over every day of ``daily``, anchored to its closes."""
        if hours < 1 or HOURS_PER_DAY % hours:
            msg = f"bars of {hours}h do not divide a UTC day"
            raise ValueError(msg)
        per_day = HOURS_PER_DAY // hours
        bar_ms = hours * MS_PER_HOUR
        day_ms = ((daily.index - _EPOCH) // pd.Timedelta(milliseconds=1)).to_numpy()
        open_ms = (day_ms[:, None] + np.arange(per_day) * bar_ms).ravel()
        columns: dict[str, np.ndarray] = {}
        listed_days = gap_bars = mismatches = 0
        max_gap = 0.0
        for symbol in daily.columns:
            close = daily[symbol].to_numpy(dtype=float)
            listed = ~np.isnan(close)
            raw = self._bar_closes(hourly[symbol], open_ms, bar_ms, hours)
            end = raw[per_day - 1 :: per_day]
            agree = np.abs(end - close) <= DAY_END_TOLERANCE * np.abs(close)
            listed_days += int(listed.sum())
            mismatches += int((listed & ~agree).sum())
            both = listed & ~np.isnan(end)
            if both.any():
                max_gap = max(
                    max_gap, float((np.abs(end - close)[both] / close[both]).max())
                )
            listed_bar = np.repeat(listed, per_day)
            gap_bars += int((listed_bar & np.isnan(raw)).sum()) - int(
                (listed & np.isnan(end)).sum()
            )
            # A paused hour trades nowhere: carry the last close, earn nothing.
            filled = pd.Series(raw).ffill().to_numpy()
            filled = np.where(listed_bar, filled, np.nan)
            filled[per_day - 1 :: per_day] = close
            columns[symbol] = filled
        index = pd.to_datetime(open_ms, unit="ms")
        quality = BarQualitySchema(
            hours=hours,
            listed_days=listed_days,
            gap_bars=gap_bars,
            day_end_mismatches=mismatches,
            max_day_end_gap=max_gap,
        )
        logger.info(
            "%dh bars: %d gap bars, %d/%d day closes disagree with the daily bar",
            hours,
            gap_bars,
            mismatches,
            listed_days,
        )
        return IntradayDataSchema(
            hours=hours, bars=pd.DataFrame(columns, index=index), quality=quality
        )

    @staticmethod
    def _bar_closes(
        frame: pd.DataFrame, open_ms: np.ndarray, bar_ms: int, hours: int
    ) -> np.ndarray:
        """Close of each complete bar at ``open_ms``; NaN where hours are missing."""
        grouped = frame.groupby(frame["open_time_ms"] // bar_ms * bar_ms)["close"]
        complete = grouped.last()[grouped.count() == hours]
        values: np.ndarray = complete.reindex(open_ms).to_numpy(dtype=float)
        return values
