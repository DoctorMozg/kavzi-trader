import logging
from datetime import UTC, datetime
from typing import Protocol

from kavzi_trader.strategies.trend.trend_gate_log import TrendGateLog
from kavzi_trader.strategies.trend.trend_gate_review_schema import (
    TrendGateReviewSchema,
)

logger = logging.getLogger(__name__)


class EntryGate(Protocol):
    async def review(self, symbol: str, as_of: datetime) -> TrendGateReviewSchema: ...


class GateReporter(Protocol):
    async def record_gate_review(self, review: TrendGateReviewSchema) -> None: ...


class ShadowGateRunner:
    """Reviews an entry and logs the verdict; the trade never waits on it."""

    def __init__(
        self,
        gate: EntryGate,
        log: TrendGateLog,
        reporter: GateReporter | None = None,
    ) -> None:
        self._gate = gate
        self._log = log
        self._reporter = reporter

    async def review_entry(self, symbol: str, as_of_ms: int) -> None:
        as_of = datetime.fromtimestamp(as_of_ms / 1000, tz=UTC)
        try:
            review = await self._gate.review(symbol, as_of)
        except Exception:
            # Shadow mode: a failed review is missing data, never a trading error.
            logger.exception(
                "Shadow trend gate failed for %s at %s",
                symbol,
                as_of,
                extra={"symbol": symbol},
            )
            return
        self._log.append(review)
        if self._reporter is None:
            return
        try:
            await self._reporter.record_gate_review(review)
        except Exception:
            logger.exception(
                "Shadow trend gate report failed for %s",
                symbol,
                extra={"symbol": symbol},
            )
