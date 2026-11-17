from datetime import UTC, datetime
from pathlib import Path

import pytest

from kavzi_trader.strategies.trend.shadow_gate_runner import ShadowGateRunner
from kavzi_trader.strategies.trend.trend_gate_log import TrendGateLog
from kavzi_trader.strategies.trend.trend_gate_review_schema import (
    TrendGateReviewSchema,
)

AS_OF_MS = 1_784_160_060_000


class StubGate:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def review(self, symbol: str, as_of: datetime) -> TrendGateReviewSchema:
        if self._error is not None:
            raise self._error
        return TrendGateReviewSchema(
            symbol=symbol,
            as_of=as_of,
            decision="KEEP",
            samples=[],
            coin_headlines=0,
            other_headlines=0,
            prompt_sha="abc",
        )


def _runner(gate: StubGate, log: TrendGateLog) -> ShadowGateRunner:
    return ShadowGateRunner(gate, log)


class TestShadowGateRunner:
    async def test_logs_the_review_at_the_intent_time(self, tmp_path: Path) -> None:
        log = TrendGateLog(tmp_path / "gate.jsonl")

        await _runner(StubGate(), log).review_entry("SOLUSDT", AS_OF_MS)

        (review,) = log.read()
        assert review.symbol == "SOLUSDT"
        assert review.as_of == datetime.fromtimestamp(AS_OF_MS / 1000, tz=UTC)

    async def test_a_failed_review_is_logged_not_raised(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        log = TrendGateLog(tmp_path / "gate.jsonl")

        await _runner(StubGate(TimeoutError("slow")), log).review_entry(
            "SOLUSDT", AS_OF_MS
        )

        assert log.read() == []
        assert "Shadow trend gate failed for SOLUSDT" in caplog.text
