import logging
from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.brain.agent.decision_dedup import DecisionDeduplicator
from kavzi_trader.brain.schemas.dependencies import ScoutDependenciesSchema
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema

logger = logging.getLogger(__name__)

_SKIP_ERROR = ScoutDecisionSchema(
    verdict="SKIP",
    reason="agent_error",
    pattern_detected=None,
)

_SKIP_NO_CANDLES = ScoutDecisionSchema(
    verdict="SKIP",
    reason="agent_error",
    pattern_detected=None,
)


class ScoutRunner(Protocol):
    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema: ...


class ScoutDepsFetcher(Protocol):
    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema: ...


class ScoutPipelineResultSchema(BaseModel):
    """Outcome of the Scout pipeline stage.

    Captures everything the caller (``AgentRouter.run``) needs to decide
    whether to stop the pipeline or escalate to the Analyst tier, without
    forcing the caller to re-read internal Scout state.

    ``stop`` is True when:
    * Scout deps have no candles (transient data gap).
    * The Scout agent raised an exception (sentinel SKIP, not cached).
    * The Scout verdict is anything other than ``INTERESTING``.

    ``cached`` is True only when the verdict was served from the dedup
    cache without re-invoking the Scout LLM.
    """

    decision: Annotated[ScoutDecisionSchema, Field(...)]
    stop: Annotated[bool, Field(...)]
    cached: Annotated[bool, Field(default=False)]
    bar_close: Annotated[datetime | None, Field(default=None)]
    pattern: Annotated[str | None, Field(default=None, max_length=200)]
    reason: Annotated[Literal["no_candles", "agent_error", "verdict", "ok"], Field(...)]

    model_config = ConfigDict(frozen=True)


class ScoutPipeline:
    """Orchestrates the Scout stage: fetch deps, dedup, invoke, cache.

    Extracted from ``AgentRouter`` so the router's ``run`` method can
    delegate Scout orchestration in one call and concentrate on Analyst
    and Trader escalation logic. Preserves the original behaviour exactly
    — including log messages, sentinel decisions, and dedup semantics.
    """

    def __init__(
        self,
        scout: ScoutRunner,
        dedup: DecisionDeduplicator,
    ) -> None:
        self._scout = scout
        self._dedup = dedup

    async def run(
        self,
        symbol: str,
        deps_provider: ScoutDepsFetcher,
    ) -> ScoutPipelineResultSchema:
        """Execute the Scout stage for ``symbol``.

        * Fetches Scout dependencies via the provider.
        * Short-circuits on empty candles with a SKIP result (no cache).
        * Consults the dedup cache keyed on (symbol, bar_close).
        * Otherwise invokes the Scout agent; caches only successful runs.
        """
        scout_deps = await self._fetch_scout_deps(symbol, deps_provider)

        if not scout_deps.recent_candles:
            logger.warning(
                "Scout deps for %s have no candles; skipping pipeline",
                symbol,
            )
            return ScoutPipelineResultSchema(
                decision=_SKIP_NO_CANDLES,
                stop=True,
                cached=False,
                bar_close=None,
                pattern=None,
                reason="no_candles",
            )

        # Scout bar-close dedup: deterministic filter produces the same
        # verdict for the same candle, so cache both INTERESTING and SKIP.
        current_scout_bar = scout_deps.recent_candles[-1].close_time
        cached_scout = self._dedup.scout_hit(symbol, current_scout_bar)
        if cached_scout is not None:
            logger.info(
                "Scout dedup hit for %s: bar close_time=%s already"
                " evaluated (cached verdict=%s)",
                symbol,
                current_scout_bar,
                cached_scout.verdict,
            )
            return ScoutPipelineResultSchema(
                decision=cached_scout,
                stop=cached_scout.verdict != "INTERESTING",
                cached=True,
                bar_close=current_scout_bar,
                pattern=cached_scout.pattern_detected,
                reason="verdict" if cached_scout.verdict != "INTERESTING" else "ok",
            )

        raw = await self._invoke_scout(symbol, scout_deps)
        if raw is None:
            # Scout raised. Don't cache the sentinel SKIP_ERROR — a
            # transient exception must allow retry on the next cycle
            # instead of poisoning the dedup cache with SKIP for the
            # whole bar.
            return ScoutPipelineResultSchema(
                decision=_SKIP_ERROR,
                stop=True,
                cached=False,
                bar_close=current_scout_bar,
                pattern=None,
                reason="agent_error",
            )

        self._dedup.cache_scout(
            symbol,
            bar_close=current_scout_bar,
            result=raw,
        )
        return ScoutPipelineResultSchema(
            decision=raw,
            stop=raw.verdict != "INTERESTING",
            cached=False,
            bar_close=current_scout_bar,
            pattern=raw.pattern_detected,
            reason="verdict" if raw.verdict != "INTERESTING" else "ok",
        )

    async def _fetch_scout_deps(
        self,
        symbol: str,
        deps_provider: ScoutDepsFetcher,
    ) -> ScoutDependenciesSchema:
        return await deps_provider.get_scout(symbol)

    async def _invoke_scout(
        self,
        symbol: str,
        deps: ScoutDependenciesSchema,
    ) -> ScoutDecisionSchema | None:
        try:
            result = await self._scout.run(deps)
        except Exception:
            logger.exception("Scout agent failed for %s", symbol)
            return None
        return result
