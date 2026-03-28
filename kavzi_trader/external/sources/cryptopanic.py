import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.schemas import CryptoPanicDataSchema

logger = logging.getLogger(__name__)

_CRYPTOPANIC_URL = "https://cryptopanic.com/api/developer/v2/posts/"
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
        logger.info("Fetching CryptoPanic news sentiment")
        try:
            resp = await self._client.get(
                _CRYPTOPANIC_URL,
                params={
                    "auth_token": self._api_key,
                    "currencies": "BTC,ETH",
                    "kind": "news",
                    "public": "true",
                },
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("status") == "api_error":
                logger.warning(
                    "CryptoPanic API error: %s",
                    body.get("info", "unknown"),
                )
                return None
            posts: list[dict[str, object]] = body.get("results", [])
            posts = posts[: self._max_results]
        except Exception:
            logger.exception("CryptoPanic fetch failed")
            return None
        else:
            result = self._parse_posts(posts)
            logger.info(
                "CryptoPanic fetched: posts=%d bullish=%d bearish=%d "
                "neutral=%d score=%.2f",
                len(posts),
                result.bullish_count,
                result.bearish_count,
                result.neutral_count,
                result.sentiment_score,
                extra={
                    "posts_count": len(posts),
                    "bullish": result.bullish_count,
                    "bearish": result.bearish_count,
                    "sentiment_score": float(result.sentiment_score),
                },
            )
            return result

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
