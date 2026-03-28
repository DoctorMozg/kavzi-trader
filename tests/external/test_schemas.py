from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.external.schemas import (
    CryptoPanicDataSchema,
    DeribitDvolDataSchema,
    ExternalDataSnapshotSchema,
    FearGreedDataSchema,
    SentimentSummarySchema,
)


def test_snapshot_is_empty_when_all_none() -> None:
    snapshot = ExternalDataSnapshotSchema()
    assert snapshot.is_empty() is True


def test_snapshot_not_empty_with_deribit() -> None:
    snapshot = ExternalDataSnapshotSchema(
        deribit_dvol=DeribitDvolDataSchema(
            dvol_index=Decimal("50.0"),
            btc_put_call_ratio=Decimal("0.7"),
            fetched_at=datetime.now(UTC),
        ),
    )
    assert snapshot.is_empty() is False


def test_snapshot_not_empty_with_fear_greed() -> None:
    snapshot = ExternalDataSnapshotSchema(
        fear_greed=FearGreedDataSchema(
            value=42,
            classification="Fear",
            fetched_at=datetime.now(UTC),
        ),
    )
    assert snapshot.is_empty() is False


def test_snapshot_not_empty_with_cryptopanic() -> None:
    snapshot = ExternalDataSnapshotSchema(
        cryptopanic=CryptoPanicDataSchema(
            bullish_count=5,
            bearish_count=3,
            neutral_count=2,
            sentiment_score=Decimal("0.2"),
            fetched_at=datetime.now(UTC),
        ),
    )
    assert snapshot.is_empty() is False


def test_sentiment_summary_bias_literal() -> None:
    for bias in ("BULLISH", "BEARISH", "NEUTRAL"):
        summary = SentimentSummarySchema(
            summary="test",
            sentiment_bias=bias,
            confidence_adjustment=Decimal("0.0"),
        )
        assert summary.sentiment_bias == bias


def test_sentiment_summary_frozen() -> None:
    summary = SentimentSummarySchema(
        summary="test",
        sentiment_bias="NEUTRAL",
        confidence_adjustment=Decimal("0.0"),
    )
    try:
        summary.summary = "changed"  # type: ignore[misc]
        msg = "Expected frozen model to raise"
        raise AssertionError(msg)
    except Exception:
        pass
