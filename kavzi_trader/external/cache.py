import logging
from datetime import UTC, datetime

from pydantic import BaseModel

from kavzi_trader.external.schemas import (
    ExternalDataSnapshotSchema,
    SentimentSummarySchema,
)

logger = logging.getLogger(__name__)


class ExternalDataCache:
    """In-memory store for external data and synthesized sentiment.

    Data is replaced every cycle — no TTL needed. The loop overwrites
    the snapshot and summary each run. Per-source last-successful values
    are kept separately so the loop can fall back on fetch failure.
    """

    def __init__(self) -> None:
        self._snapshot = ExternalDataSnapshotSchema.model_validate({})
        self._sentiment_summary: SentimentSummarySchema | None = None
        self._sentiment_updated_at: datetime | None = None
        self._last_successful: dict[str, BaseModel] = {}
        self._sources_degraded: list[str] = []

    def set_snapshot(self, snapshot: ExternalDataSnapshotSchema) -> None:
        self._snapshot = snapshot
        logger.debug("External data snapshot updated")

    def get_snapshot(self) -> ExternalDataSnapshotSchema:
        return self._snapshot

    def set_sentiment_summary(self, summary: SentimentSummarySchema) -> None:
        self._sentiment_summary = summary
        self._sentiment_updated_at = datetime.now(UTC)
        logger.debug(
            "Sentiment summary updated: bias=%s adjustment=%s",
            summary.sentiment_bias,
            summary.confidence_adjustment,
        )

    def get_sentiment_summary(self) -> SentimentSummarySchema | None:
        return self._sentiment_summary

    def get_sentiment_updated_at(self) -> datetime | None:
        return self._sentiment_updated_at

    # -- Per-source last-successful cache --

    def set_last_successful(self, name: str, data: BaseModel) -> None:
        self._last_successful[name] = data

    def get_last_successful(
        self,
        name: str,
        expected_type: type[BaseModel],
    ) -> BaseModel | None:
        value = self._last_successful.get(name)
        if value is not None and isinstance(value, expected_type):
            return value
        return None

    def set_sources_degraded(self, names: list[str]) -> None:
        self._sources_degraded = names

    def get_sources_degraded(self) -> list[str]:
        return list(self._sources_degraded)
