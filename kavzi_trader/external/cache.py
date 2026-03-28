import logging

from kavzi_trader.external.schemas import (
    ExternalDataSnapshotSchema,
    SentimentSummarySchema,
)

logger = logging.getLogger(__name__)


class ExternalDataCache:
    """In-memory store for external data and synthesized sentiment.

    Data is replaced every cycle — no TTL needed. The loop overwrites
    the snapshot and summary each run.
    """

    def __init__(self) -> None:
        self._snapshot = ExternalDataSnapshotSchema.model_validate({})
        self._sentiment_summary: SentimentSummarySchema | None = None

    def set_snapshot(self, snapshot: ExternalDataSnapshotSchema) -> None:
        self._snapshot = snapshot
        logger.debug("External data snapshot updated")

    def get_snapshot(self) -> ExternalDataSnapshotSchema:
        return self._snapshot

    def set_sentiment_summary(self, summary: SentimentSummarySchema) -> None:
        self._sentiment_summary = summary
        logger.debug(
            "Sentiment summary updated: bias=%s adjustment=%s",
            summary.sentiment_bias,
            summary.confidence_adjustment,
        )

    def get_sentiment_summary(self) -> SentimentSummarySchema | None:
        return self._sentiment_summary
