import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.schemas import CryptoPanicDataSchema

logger = logging.getLogger(__name__)

_CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/"
_TIMEOUT_S = 10.0


class CryptoPanicSource(ExternalSource):
    """Fetches news sentiment from CryptoPanic API."""

    def __init__(
        self,
        api_key: str,
        max_results: int = 20,
        max_headlines: int = 5,
    ) -> None:
        self._api_key = api_key
        self._max_results = max_results
        self._max_headlines = max_headlines
        self._client = httpx.AsyncClient(timeout=_TIMEOUT_S)

    @property
    def name(self) -> str:
        return "cryptopanic"

    async def fetch(self) -> CryptoPanicDataSchema | None:
        try:
            resp = await self._client.get(
                _CRYPTOPANIC_URL,
                params={
                    "auth_token": self._api_key,
                    "currencies": "BTC,ETH",
                    "filter": "rising",
                    "kind": "news",
                    "public": "true",
                },
            )
            resp.raise_for_status()
            posts: list[dict[str, object]] = resp.json().get("results", [])
            posts = posts[: self._max_results]
            return self._parse_posts(posts)
        except Exception:
            logger.exception("CryptoPanic fetch failed")
            return None

    def _parse_posts(
        self,
        posts: list[dict[str, object]],
    ) -> CryptoPanicDataSchema:
        bullish = 0
        bearish = 0
        neutral = 0
        headlines: list[str] = []

        for post in posts:
            title = str(post.get("title", ""))
            if title:
                headlines.append(title)

            votes = post.get("votes", {})
            if not isinstance(votes, dict):
                neutral += 1
                continue

            positive = int(votes.get("positive", 0))
            negative = int(votes.get("negative", 0))

            if positive > negative:
                bullish += 1
            elif negative > positive:
                bearish += 1
            else:
                neutral += 1

        total = max(len(posts), 1)
        score = Decimal(str((bullish - bearish) / total))

        return CryptoPanicDataSchema(
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
            top_headlines=headlines[: self._max_headlines],
            sentiment_score=score,
            fetched_at=datetime.now(UTC),
        )
