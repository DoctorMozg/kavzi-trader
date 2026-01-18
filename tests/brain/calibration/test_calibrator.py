import pytest

from kavzi_trader.brain.calibration.calibrator import ConfidenceCalibrator


class DummyHistoryStore:
    def __init__(self, accuracy: float | None) -> None:
        self._accuracy = accuracy
        self.records: list[tuple[str, bool]] = []

    async def get_accuracy(self, bucket: str) -> float | None:
        return self._accuracy

    async def record(self, bucket: str, was_correct: bool) -> None:
        self.records.append((bucket, was_correct))


@pytest.mark.asyncio()
async def test_calibrator_defaults_to_bucket_value() -> None:
    history = DummyHistoryStore(accuracy=None)
    calibrator = ConfidenceCalibrator(history)
    calibrated = await calibrator.calibrate(0.92)
    assert calibrated == 0.65, "Expected default calibration for 0.9+ bucket."


@pytest.mark.asyncio()
async def test_calibrator_uses_history_accuracy() -> None:
    history = DummyHistoryStore(accuracy=0.72)
    calibrator = ConfidenceCalibrator(history)
    calibrated = await calibrator.calibrate(0.75)
    assert calibrated == 0.72, "Expected historical accuracy to be used."


@pytest.mark.asyncio()
async def test_calibrator_records_outcome() -> None:
    history = DummyHistoryStore(accuracy=None)
    calibrator = ConfidenceCalibrator(history)
    await calibrator.record_outcome("dec-1", 0.8, True)
    assert history.records, "Expected a recorded outcome."
