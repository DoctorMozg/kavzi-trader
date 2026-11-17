from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kavzi_trader.news.news_store import NewsStore

AS_OF = datetime(2026, 7, 16, 12, tzinfo=UTC)
LAG = timedelta(hours=2)
WINDOW = timedelta(hours=72)


class TestNewsStore:
    def test_keeps_the_first_seen_title_of_a_url(
        self, tmp_path: Path, make_item
    ) -> None:
        store = NewsStore(tmp_path)
        published = AS_OF - timedelta(hours=5)
        store.add([make_item("u1", published, title="first")])

        added = store.add([make_item("u1", published, title="edited")])

        assert added == 0
        [item] = NewsStore(tmp_path).query(AS_OF, WINDOW, LAG)
        assert item.title == "first"

    def test_hides_items_inside_the_lag_and_outside_the_window(
        self, tmp_path: Path, make_item
    ) -> None:
        store = NewsStore(tmp_path)
        store.add(
            [
                make_item("fresh", AS_OF - timedelta(hours=1)),
                make_item("visible", AS_OF - timedelta(hours=3)),
                make_item("old", AS_OF - timedelta(hours=80)),
                make_item("future", AS_OF + timedelta(hours=1)),
            ]
        )

        urls = [i.url for i in store.query(AS_OF, WINDOW, LAG)]

        assert urls == ["visible"]

    def test_day_precision_items_wait_a_full_day(
        self, tmp_path: Path, make_item
    ) -> None:
        store = NewsStore(tmp_path)
        same_day = datetime(2026, 7, 16, tzinfo=UTC)
        store.add([make_item("today", same_day, precision="day")])

        assert store.query(AS_OF, WINDOW, LAG) == []
        later = same_day + timedelta(hours=32)
        assert [i.url for i in store.query(later, WINDOW, LAG)] == ["today"]

    def test_files_split_by_publish_month(self, tmp_path: Path, make_item) -> None:
        NewsStore(tmp_path).add(
            [make_item("a", AS_OF), make_item("b", AS_OF + timedelta(days=20))]
        )

        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "2026-07.jsonl",
            "2026-08.jsonl",
        ]

    def test_rejects_a_naive_as_of(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            NewsStore(tmp_path).query(datetime(2026, 7, 16), WINDOW, LAG)  # noqa: DTZ001
