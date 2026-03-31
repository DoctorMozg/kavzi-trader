from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.external.schemas import (
    DeribitDvolDataSchema,
    ExternalDataSnapshotSchema,
    FearGreedDataSchema,
    SentimentSummarySchema,
)


def _make_snapshot() -> ExternalDataSnapshotSchema:
    now = datetime.now(UTC)
    return ExternalDataSnapshotSchema(
        deribit_dvol=DeribitDvolDataSchema(
            dvol_index=Decimal("55.0"),
            btc_put_call_ratio=Decimal("0.65"),
            fetched_at=now,
        ),
        fear_greed=FearGreedDataSchema(
            value=35,
            classification="Fear",
            fetched_at=now,
        ),
    )


def _make_summary() -> SentimentSummarySchema:
    return SentimentSummarySchema(
        summary="Mild fear in the market with moderate options volatility.",
        sentiment_bias="BEARISH",
        confidence_adjustment=Decimal("-0.05"),
    )


def test_cache_starts_empty() -> None:
    cache = ExternalDataCache()
    snapshot = cache.get_snapshot()
    assert snapshot.is_empty()
    assert cache.get_sentiment_summary() is None


def test_set_and_get_snapshot() -> None:
    cache = ExternalDataCache()
    snapshot = _make_snapshot()
    cache.set_snapshot(snapshot)
    retrieved = cache.get_snapshot()
    assert retrieved.deribit_dvol is not None
    assert retrieved.deribit_dvol.dvol_index == Decimal("55.0")
    assert retrieved.fear_greed is not None
    assert retrieved.fear_greed.value == 35
    assert retrieved.ccdata_news is None


def test_set_and_get_sentiment_summary() -> None:
    cache = ExternalDataCache()
    summary = _make_summary()
    cache.set_sentiment_summary(summary)
    retrieved = cache.get_sentiment_summary()
    assert retrieved is not None
    assert retrieved.sentiment_bias == "BEARISH"
    assert retrieved.confidence_adjustment == Decimal("-0.05")


def test_snapshot_overwrite() -> None:
    cache = ExternalDataCache()
    cache.set_snapshot(_make_snapshot())
    empty = ExternalDataSnapshotSchema()
    cache.set_snapshot(empty)
    assert cache.get_snapshot().is_empty()


def test_summary_overwrite() -> None:
    cache = ExternalDataCache()
    cache.set_sentiment_summary(_make_summary())
    new_summary = SentimentSummarySchema(
        summary="Market is neutral.",
        sentiment_bias="NEUTRAL",
        confidence_adjustment=Decimal("0.00"),
    )
    cache.set_sentiment_summary(new_summary)
    retrieved = cache.get_sentiment_summary()
    assert retrieved is not None
    assert retrieved.sentiment_bias == "NEUTRAL"
