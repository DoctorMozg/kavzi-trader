import asyncio
import logging
import time
from typing import Protocol

from pydantic import BaseModel

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.external.circuit_breaker import CircuitBreaker
from kavzi_trader.external.config import CircuitBreakerConfigSchema
from kavzi_trader.external.schemas import (
    CCDataNewsDataSchema,
    DeribitDvolDataSchema,
    ExternalDataSnapshotSchema,
    FearGreedDataSchema,
    SentimentSummarySchema,
)

logger = logging.getLogger(__name__)


class SentimentSynthesizerProtocol(Protocol):
    async def synthesize(
        self,
        snapshot: ExternalDataSnapshotSchema,
        sources_degraded: list[str],
    ) -> SentimentSummarySchema | None: ...


class ExternalSentimentLoop:
    """Combined fetch + synthesize loop.

    Each cycle:
    1. Fetch all sources in parallel via asyncio.gather
    2. Build snapshot (with stale fallback) and store in cache
    3. Synthesize via LLM and store summary in cache
    """

    def __init__(
        self,
        sources: list[ExternalSource],
        synthesizer: SentimentSynthesizerProtocol | None,
        cache: ExternalDataCache,
        interval_s: int = 300,
        circuit_breaker_config: CircuitBreakerConfigSchema | None = None,
    ) -> None:
        self._sources = sources
        self._synthesizer = synthesizer
        self._cache = cache
        self._interval_s = interval_s
        cb_cfg = circuit_breaker_config or CircuitBreakerConfigSchema()
        self._breakers: dict[str, CircuitBreaker] = {
            s.name: CircuitBreaker(
                failure_threshold=cb_cfg.failure_threshold,
                cooldown_s=float(cb_cfg.cooldown_s),
                max_cooldown_s=float(cb_cfg.max_cooldown_s),
                max_reopen_count=cb_cfg.max_reopen_count,
            )
            for s in sources
        }

    async def warm_up(self) -> None:
        """Run a single fetch+synthesize cycle before the main loop starts."""
        logger.info("ExternalSentimentLoop warming up (pre-fetching all sources)")
        await self._cycle()
        logger.info("ExternalSentimentLoop warm-up complete")

    async def run(self) -> None:
        logger.info(
            "ExternalSentimentLoop started with %d sources, interval=%ds",
            len(self._sources),
            self._interval_s,
        )
        while True:
            await self._cycle()
            await asyncio.sleep(self._interval_s)

    async def _cycle(self) -> None:
        t0 = time.monotonic()

        # 1. Fetch all sources in parallel (with stale fallback)
        snapshot, sources_degraded = await self._fetch_all()
        self._cache.set_snapshot(snapshot)
        self._cache.set_sources_degraded(sources_degraded)

        # 2. Synthesize if enabled
        if self._synthesizer is not None and not snapshot.is_empty():
            try:
                summary = await self._synthesizer.synthesize(snapshot, sources_degraded)
                if summary is not None:
                    self._cache.set_sentiment_summary(summary)
            except Exception:
                logger.exception("Sentiment synthesis failed, keeping stale summary")
        elif snapshot.is_empty():
            logger.debug("All external sources returned None, skipping synthesis")

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "ExternalSentimentLoop cycle complete in %.1fms",
            elapsed_ms,
            extra={"elapsed_ms": round(elapsed_ms, 1)},
        )

    async def _fetch_all(
        self,
    ) -> tuple[ExternalDataSnapshotSchema, list[str]]:
        results = await asyncio.gather(
            *(self._fetch_one(source) for source in self._sources),
            return_exceptions=True,
        )

        source_data: dict[str, BaseModel] = {}
        sources_degraded: list[str] = []

        for source, result in zip(self._sources, results, strict=True):
            if isinstance(result, BaseException):
                logger.exception(
                    "External source %s raised an exception",
                    source.name,
                    exc_info=result,
                )
                result = None  # noqa: PLW2901 — treat exception as missing
            if result is not None:
                # Fresh data — update last-successful cache
                source_data[source.name] = result
                self._cache.set_last_successful(source.name, result)
            else:
                # Fetch failed — try stale fallback
                stale = self._cache.get_last_successful(source.name, BaseModel)
                if stale is not None:
                    source_data[source.name] = stale
                    sources_degraded.append(source.name)
                    logger.warning(
                        "External source %s failed, using stale cached value",
                        source.name,
                    )

        fetched_fresh = sorted(
            name for name in source_data if name not in sources_degraded
        )
        failed = sorted(
            source.name for source in self._sources if source.name not in source_data
        )
        logger.info(
            "External fetch complete: fresh=%s stale=%s failed=%s",
            fetched_fresh or "none",
            sources_degraded or "none",
            failed or "none",
            extra={
                "fetched_fresh": fetched_fresh,
                "stale": sources_degraded,
                "failed": failed,
            },
        )

        return (
            ExternalDataSnapshotSchema(
                deribit_dvol=self._typed_get(
                    source_data, "deribit_dvol", DeribitDvolDataSchema
                ),
                fear_greed=self._typed_get(
                    source_data, "fear_greed", FearGreedDataSchema
                ),
                ccdata_news=self._typed_get(
                    source_data, "ccdata_news", CCDataNewsDataSchema
                ),
            ),
            sources_degraded,
        )

    async def _fetch_one(self, source: ExternalSource) -> BaseModel | None:
        breaker = self._breakers.get(source.name)
        if breaker is not None and not breaker.should_allow():
            logger.debug(
                "Circuit open for %s, skipping fetch",
                source.name,
            )
            return None
        try:
            result = await source.fetch()
        except Exception:
            logger.exception(
                "External source %s fetch failed",
                source.name,
            )
            result = None
        if breaker is not None:
            if result is not None:
                breaker.record_success()
            else:
                breaker.record_failure()
        return result

    @staticmethod
    def _typed_get[T: BaseModel](
        data: dict[str, BaseModel],
        key: str,
        expected_type: type[T],
    ) -> T | None:
        value = data.get(key)
        if value is None:
            return None
        if isinstance(value, expected_type):
            return value
        return None
