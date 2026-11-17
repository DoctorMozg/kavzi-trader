from datetime import UTC, datetime

import pytest

from kavzi_trader.news.news_item_schema import NewsItemSchema

SEEN_AT = datetime(2026, 11, 17, 12, tzinfo=UTC)


def rss(*items: tuple[str, str, str]) -> str:
    """RSS 2.0 text from (title, link, pubDate) triples."""
    body = "".join(
        f"<item><title>{t}</title><link>{link}</link><pubDate>{d}</pubDate>"
        "<category>Markets</category></item>"
        for t, link, d in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


@pytest.fixture
def make_item():
    def _make(
        url: str, published: datetime, precision: str = "exact", title: str = "t"
    ) -> NewsItemSchema:
        return NewsItemSchema.model_validate(
            {
                "url": url,
                "title": title,
                "source": "test",
                "published_at": published,
                "precision": precision,
                "first_seen_at": SEEN_AT,
            }
        )

    return _make
