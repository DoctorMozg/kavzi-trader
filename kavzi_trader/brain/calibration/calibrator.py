import logging
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from kavzi_trader.brain.calibration.history import ConfidenceHistoryStore

logger = logging.getLogger(__name__)


class _CalibrationBucket(BaseModel):
    name: str
    low: float
    high: float
    default_accuracy: float
    model_config = ConfigDict(frozen=True)


DEFAULT_BUCKETS: list[_CalibrationBucket] = [
    _CalibrationBucket(
        name="raw_0_9_plus",
        low=0.9,
        high=1.01,
        default_accuracy=0.65,
    ),
    _CalibrationBucket(
        name="raw_0_8_0_9",
        low=0.8,
        high=0.9,
        default_accuracy=0.55,
    ),
    _CalibrationBucket(
        name="raw_0_7_0_8",
        low=0.7,
        high=0.8,
        default_accuracy=0.45,
    ),
    _CalibrationBucket(
        name="raw_below_0_7",
        low=0.0,
        high=0.7,
        default_accuracy=0.35,
    ),
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
        for b in DEFAULT_BUCKETS:
            if b.low <= clamped < b.high:
                return b.name
        return DEFAULT_BUCKETS[-1].name

    def _default_for(self, bucket: str) -> float:
        for b in DEFAULT_BUCKETS:
            if b.name == bucket:
                return b.default_accuracy
        return DEFAULT_BUCKETS[-1].default_accuracy
