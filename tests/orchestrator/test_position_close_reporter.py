from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.orchestrator.loops.position_close_reporter import (
    PositionCloseReporter,
)

_POSITION = PositionSchema.model_construct(id="pos-1", symbol="BTCUSDT")


@pytest.mark.asyncio
async def test_report_forwards_to_recorder() -> None:
    recorder = AsyncMock()

    await PositionCloseReporter(recorder, "position").report(
        _POSITION,
        "TP",
        Decimal(110),
    )

    recorder.record_position_close.assert_awaited_once_with(
        _POSITION,
        "TP",
        Decimal(110),
    )


@pytest.mark.asyncio
async def test_report_swallows_and_logs_recorder_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    recorder = AsyncMock()
    recorder.record_position_close.side_effect = RuntimeError("ui down")

    await PositionCloseReporter(recorder, "execution").report(
        _POSITION,
        "TP",
        Decimal(110),
    )

    assert "Failed to report position close for BTCUSDT" in caplog.text


@pytest.mark.asyncio
async def test_report_without_recorder_is_noop() -> None:
    await PositionCloseReporter(None, "execution").report(
        _POSITION,
        "TP",
        Decimal(110),
    )
