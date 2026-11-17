import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

from kavzi_trader.news.news_item_schema import NewsItemSchema

logger = logging.getLogger(__name__)


class NewsStore:
    """Append-only monthly JSONL files of headlines, deduplicated by URL."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._items = {item.url: item for item in self._load()}

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, url: object) -> bool:
        return url in self._items

    def add(self, items: Iterable[NewsItemSchema]) -> int:
        """Stores unseen URLs only, so the first-seen title is never overwritten."""
        fresh: dict[str, NewsItemSchema] = {}
        for item in items:
            if item.url not in self._items and item.url not in fresh:
                fresh[item.url] = item
        self._root.mkdir(parents=True, exist_ok=True)
        for item in fresh.values():
            self._items[item.url] = item
            path = self._root / f"{item.published_at:%Y-%m}.jsonl"
            with path.open("a", encoding="utf-8") as out:
                out.write(item.model_dump_json() + "\n")
        logger.info("Stored %d new headlines (%d total)", len(fresh), len(self._items))
        return len(fresh)

    def query(
        self, as_of: datetime, window: timedelta, lag: timedelta
    ) -> list[NewsItemSchema]:
        """Headlines a reader at ``as_of`` could have seen, newest first."""
        if as_of.tzinfo is None:
            msg = f"as_of must be timezone-aware, got {as_of}"
            raise ValueError(msg)
        visible = [
            item
            for item in self._items.values()
            if as_of - window <= item.published_at and item.available_at(lag) <= as_of
        ]
        return sorted(visible, key=lambda item: item.published_at, reverse=True)

    def _load(self) -> list[NewsItemSchema]:
        if not self._root.exists():
            return []
        return [
            NewsItemSchema.model_validate_json(line)
            for path in sorted(self._root.glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
