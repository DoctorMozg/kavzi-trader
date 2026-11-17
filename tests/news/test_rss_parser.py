from datetime import UTC, datetime

from kavzi_trader.news.coin_tagger import CoinTagger
from kavzi_trader.news.rss_parser import RssParser
from tests.news.conftest import SEEN_AT, rss


def test_parses_items_with_utc_publish_time_and_coins() -> None:
    text = rss(("Bitcoin slides", "https://x.io/a", "Tue, 17 Nov 2026 10:30:00 -0500"))

    [item] = RssParser(CoinTagger()).parse(text, "coindesk", SEEN_AT)

    assert item.published_at == datetime(2026, 11, 17, 15, 30, tzinfo=UTC)
    assert item.precision == "exact"
    assert item.coins == ("BTC",)
    assert item.first_seen_at == SEEN_AT
    assert item.source == "coindesk"


def test_skips_items_missing_a_publish_date() -> None:
    text = rss(
        ("No date", "https://x.io/b", ""),
        ("Dated", "https://x.io/c", "Tue, 17 Nov 2026 10:30:00 GMT"),
    )

    items = RssParser(CoinTagger()).parse(text, "decrypt", SEEN_AT)

    assert [i.url for i in items] == ["https://x.io/c"]
