from datetime import UTC, datetime

from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.news import NewsEventFilter
from kavzi_trader.spine.filters.news_event_schema import NewsEventSchema


def test_news_filter_blocks_within_window() -> None:
    config = FilterConfigSchema()
    now = datetime(2025, 1, 6, 12, 30, tzinfo=UTC)
    event = NewsEventSchema(
        name="FOMC",
        start_time=datetime(2025, 1, 6, 12, 0, tzinfo=UTC),
        end_time=datetime(2025, 1, 6, 13, 0, tzinfo=UTC),
    )
    news_filter = NewsEventFilter(config, time_provider=lambda: now)

    result = news_filter.evaluate(events=[event])

    assert result.is_allowed is False, "Expected news filter to block"
    assert result.reason == "FOMC", "Expected event name in reason"


def test_news_filter_allows_without_events() -> None:
    config = FilterConfigSchema()
    now = datetime(2025, 1, 6, 12, 30, tzinfo=UTC)
    news_filter = NewsEventFilter(config, time_provider=lambda: now)

    result = news_filter.evaluate(events=[])

    assert result.is_allowed is True, "Expected news filter to allow"
