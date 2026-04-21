import logging
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema

logger = logging.getLogger(__name__)


class ScoutDedupEntry(BaseModel):
    bar_close: datetime
    result: ScoutDecisionSchema
    model_config = ConfigDict(frozen=True)


class AnalystDedupEntry(BaseModel):
    bar_close: datetime
    result: AnalystDecisionSchema
    model_config = ConfigDict(frozen=True)


class TraderDedupEntry(BaseModel):
    bar_close: datetime
    analyst_hash: str
    decision: TradeDecisionSchema
    model_config = ConfigDict(frozen=True)


class DecisionDeduplicator:
    """Per-symbol bar-close dedup store for Scout / Analyst / Trader tiers.

    Holds three in-memory caches keyed by symbol. The Scout and Analyst
    caches invalidate on a new bar close_time; the Trader cache also
    invalidates when the Analyst result hash changes within the same bar.

    Intentionally not a Pydantic model: this is mutable in-process state,
    not a domain value object. The backing dicts are exposed by reference
    so legacy callers (and tests) that read or mutate them directly
    (``scout_entries.clear()``, ``"BTCUSDT" in trader_entries``) observe
    live state without a second code path.
    """

    def __init__(self) -> None:
        self._scout: dict[str, ScoutDedupEntry] = {}
        self._analyst: dict[str, AnalystDedupEntry] = {}
        self._trader: dict[str, TraderDedupEntry] = {}

    @property
    def scout_entries(self) -> dict[str, ScoutDedupEntry]:
        """Live reference to the per-symbol Scout dedup entries."""
        return self._scout

    @property
    def analyst_entries(self) -> dict[str, AnalystDedupEntry]:
        """Live reference to the per-symbol Analyst dedup entries."""
        return self._analyst

    @property
    def trader_entries(self) -> dict[str, TraderDedupEntry]:
        """Live reference to the per-symbol Trader dedup entries."""
        return self._trader

    def scout_hit(
        self,
        symbol: str,
        bar_close: datetime,
    ) -> ScoutDecisionSchema | None:
        """Return the cached Scout decision for (symbol, bar_close), else None.

        Cross-bar invalidation: a cached entry whose ``bar_close`` differs
        from the current bar is treated as a miss so the caller re-invokes
        the Scout for the new candle.
        """
        entry = self._scout.get(symbol)
        if entry is None or entry.bar_close != bar_close:
            return None
        return entry.result

    def cache_scout(
        self,
        symbol: str,
        bar_close: datetime,
        result: ScoutDecisionSchema,
    ) -> None:
        """Single write path for the Scout dedup cache."""
        self._scout[symbol] = ScoutDedupEntry(
            bar_close=bar_close,
            result=result,
        )

    def analyst_hit(
        self,
        symbol: str,
        bar_close: datetime,
    ) -> AnalystDecisionSchema | None:
        """Return the cached Analyst decision for (symbol, bar_close), else
        None. Cross-bar invalidation mirrors :meth:`scout_hit`.
        """
        entry = self._analyst.get(symbol)
        if entry is None or entry.bar_close != bar_close:
            return None
        return entry.result

    def cache_analyst(
        self,
        symbol: str,
        bar_close: datetime,
        result: AnalystDecisionSchema,
    ) -> None:
        """Single write path for the Analyst dedup cache."""
        self._analyst[symbol] = AnalystDedupEntry(
            bar_close=bar_close,
            result=result,
        )

    def trader_hit(
        self,
        symbol: str,
        analyst_hash: str,
        bar_close: datetime,
    ) -> TradeDecisionSchema | None:
        """Return the cached Trader decision for (symbol, analyst_hash,
        bar_close) if still valid; otherwise None.

        Invariant: the cache key is the 3-tuple (symbol, bar_close,
        analyst_hash). All three must match for a hit. Changing the
        ``TraderDedupEntry`` fields without updating this comparison
        would silently weaken dedup and leak stale Trader decisions
        across bars or Analyst revisions.
        """
        entry = self._trader.get(symbol)
        if (
            entry is None
            or entry.analyst_hash != analyst_hash
            or entry.bar_close != bar_close
        ):
            return None
        return entry.decision

    def cache_trader(
        self,
        symbol: str,
        analyst_hash: str,
        bar_close: datetime,
        decision: TradeDecisionSchema,
    ) -> None:
        """Single write path for the Trader dedup cache."""
        self._trader[symbol] = TraderDedupEntry(
            bar_close=bar_close,
            analyst_hash=analyst_hash,
            decision=decision,
        )
