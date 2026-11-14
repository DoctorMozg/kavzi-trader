import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx2

from kavzi_trader.commons.retry import RetryPolicySchema, retry_async
from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.schemas import CCDataNewsDataSchema

logger = logging.getLogger(__name__)

_CCDATA_NEWS_URL = "https://data-api.ccdata.io/news/v1/article/list"
_TIMEOUT_S = 10.0
_MAX_RETRIES = 3
_RETRYABLE_ERRORS = (
    httpx2.HTTPStatusError,
    httpx2.RequestError,
    json.JSONDecodeError,
    ValueError,
    KeyError,
    AttributeError,
)
_RETRY_POLICY = RetryPolicySchema(
    attempts=_MAX_RETRIES,
    backoff_base_s=1.0,
    retry_on=_RETRYABLE_ERRORS,
)
_HTTP_FORBIDDEN = 403


class CCDataNewsSource(ExternalSource):
    """Fetches news sentiment from CCData (CryptoCompare successor) API.

    No API key required. Each article includes a pre-computed SENTIMENT
    field (POSITIVE/NEGATIVE/NEUTRAL) which we aggregate into counts.

    Self-disables on 403 responses: CCData has migrated its free tier to
    require an API key, so 403 means no access — retrying is pointless.
    """

    def __init__(
        self,
        max_results: int = 20,
        max_headlines: int = 5,
    ) -> None:
        self._max_results = max_results
        self._max_headlines = max_headlines
        self._client = httpx2.AsyncClient(timeout=_TIMEOUT_S)
        self._permanently_disabled = False

    @property
    def name(self) -> str:
        return "ccdata_news"

    async def fetch(self) -> CCDataNewsDataSchema | None:
        if self._permanently_disabled:
            return None
        logger.info("Fetching CCData news sentiment")
        articles = await self._fetch_articles_with_retry()
        if articles is None:
            return None

        result = self._parse_articles(articles)
        logger.info(
            "CCData news fetched: articles=%d bullish=%d bearish=%d "
            "neutral=%d score=%.2f",
            len(articles),
            result.bullish_count,
            result.bearish_count,
            result.neutral_count,
            result.sentiment_score,
            extra={
                "articles_count": len(articles),
                "bullish": result.bullish_count,
                "bearish": result.bearish_count,
                "sentiment_score": float(result.sentiment_score),
            },
        )
        return result

    async def _fetch_articles_with_retry(self) -> list[dict[str, object]] | None:
        """Fetch raw article list with bounded retries.

        Transient network / 5xx errors are retried with exponential
        backoff (1s, 2s) across `_MAX_RETRIES` attempts. The final failure
        is logged once as an exception and `None` is returned so the
        caller's graceful-degradation path (stale cache + circuit breaker
        in `external/loop.py`) can take over.
        """
        try:
            return await retry_async(
                self._fetch_articles,
                _RETRY_POLICY,
                name="CCData news fetch",
            )
        except _RETRYABLE_ERRORS:
            logger.exception(
                "CCData news fetch failed after %d attempts",
                _MAX_RETRIES,
                extra={"attempts": _MAX_RETRIES},
            )
            return None

    async def _fetch_articles(self) -> list[dict[str, object]] | None:
        """One fetch attempt; `None` means the source is now disabled."""
        try:
            resp = await self._client.get(
                _CCDATA_NEWS_URL,
                params={
                    "lang": "EN",
                    "categories": "BTC,ETH",
                    "limit": self._max_results,
                },
            )
            resp.raise_for_status()
        except httpx2.HTTPStatusError as exc:
            if exc.response.status_code != _HTTP_FORBIDDEN:
                raise
            # 403 means access denied — the free tier now requires an API
            # key. Retrying won't help; self-disable for the session to
            # avoid log spam and wasted cycles.
            self._permanently_disabled = True
            logger.warning(
                "CCData news API returned 403 Forbidden — "
                "source disabled for this session. "
                "Set external_sources.ccdata_news.enabled=false to suppress.",
                extra={"status_code": 403},
            )
            return None
        body = resp.json()
        articles: list[dict[str, object]] = body.get("Data", [])
        return articles

    def _parse_articles(
        self,
        articles: list[dict[str, object]],
    ) -> CCDataNewsDataSchema:
        bullish = 0
        bearish = 0
        neutral = 0
        headlines: list[str] = []

        for article in articles:
            title = str(article.get("TITLE", ""))
            if title:
                headlines.append(title)

            sentiment = str(article.get("SENTIMENT", "NEUTRAL")).upper()
            if sentiment == "POSITIVE":
                bullish += 1
            elif sentiment == "NEGATIVE":
                bearish += 1
            else:
                neutral += 1

        total = max(len(articles), 1)
        score = Decimal(str((bullish - bearish) / total))

        return CCDataNewsDataSchema(
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
            top_headlines=headlines[: self._max_headlines],
            sentiment_score=score,
            fetched_at=datetime.now(UTC),
        )
