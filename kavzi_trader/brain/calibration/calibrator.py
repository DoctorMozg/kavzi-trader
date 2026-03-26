import logging
from typing import Protocol

from kavzi_trader.brain.calibration.history import ConfidenceHistoryStore

logger = logging.getLogger(__name__)

DEFAULT_BUCKETS: list[tuple[str, float, float, float]] = [
    ("raw_0_9_plus", 0.9, 1.01, 0.65),
    ("raw_0_8_0_9", 0.8, 0.9, 0.55),
    ("raw_0_7_0_8", 0.7, 0.8, 0.45),
    ("raw_below_0_7", 0.0, 0.7, 0.35),
]


class ConfidenceHistory(Protocol):
    async def get_accuracy(self, bucket: str) -> float | None: ...

    async def record(self, bucket: str, was_correct: bool) -> None: ...


class ConfidenceCalibrator:
    """
    Converts raw model confidence into historically grounded confidence.
    """

    def __init__(self, history: ConfidenceHistory | ConfidenceHistoryStore) -> None:
        self._history = history

    async def calibrate(self, raw_confidence: float) -> float:
        bucket = self._bucket(raw_confidence)
        accuracy = await self._history.get_accuracy(bucket)
        if accuracy is None:
            logger.warning(
                "No history for bucket %s, using default accuracy",
                bucket,
            )
            calibrated = self._default_for(bucket)
        else:
            calibrated = accuracy
        logger.debug(
            "Calibration: raw=%.3f bucket=%s calibrated=%.3f",
            raw_confidence,
            bucket,
            calibrated,
        )
        return calibrated

    async def record_outcome(
        self,
        decision_id: str,
        raw_confidence: float,
        was_correct: bool,
    ) -> None:
        bucket = self._bucket(raw_confidence)
        logger.debug(
            "Recording outcome: decision_id=%s bucket=%s correct=%s",
            decision_id,
            bucket,
            was_correct,
        )
        try:
            await self._history.record(bucket, was_correct)
        except Exception:
            logger.exception("Failed to record outcome for %s", decision_id)

    def _bucket(self, raw_confidence: float) -> str:
        clamped = min(max(raw_confidence, 0.0), 1.0)
        for name, low, high, _ in DEFAULT_BUCKETS:
            if low <= clamped < high:
                return name
        return DEFAULT_BUCKETS[-1][0]

    def _default_for(self, bucket: str) -> float:
        for name, _, _, default in DEFAULT_BUCKETS:
            if name == bucket:
                return default
        return DEFAULT_BUCKETS[-1][3]
