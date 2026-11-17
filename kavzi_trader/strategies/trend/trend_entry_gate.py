import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Literal

from pydantic_ai import Agent

from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.domain.trend_gate_decision import TrendGateDecisionSchema
from kavzi_trader.news.news_item_schema import NewsItemSchema
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.strategies.trend.trend_gate_config import TrendGateConfigSchema
from kavzi_trader.strategies.trend.trend_gate_review_schema import (
    TrendGateReviewSchema,
)

logger = logging.getLogger(__name__)


class TrendEntryGate:
    """Asks the LLM, several times, whether recent news contradicts a trend entry."""

    def __init__(
        self,
        agent: Agent[None, TrendGateDecisionSchema],
        prompts: PromptLoader,
        config: TrendGateConfigSchema,
        system_prompt: str,
    ) -> None:
        self._agent = agent
        self._prompts = prompts
        self._config = config
        # Every prompt change is a new trial; the hash ties a review to its prompt.
        self._prompt_sha = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]

    async def review(self, symbol: str, as_of: datetime) -> TrendGateReviewSchema:
        coin = symbol.removesuffix("USDT")
        # Reload per review: the collector appends from another process.
        items = NewsStore(self._config.news_root).query(
            as_of,
            timedelta(hours=self._config.window_h),
            timedelta(hours=self._config.lag_h),
        )
        cap = self._config.max_headlines
        mentions = [i for i in items if coin in i.coins][:cap]
        others = [i for i in items if coin not in i.coins][: cap - len(mentions)]
        samples: list[TrendGateDecisionSchema] = []
        if items:
            prompt = self._prompts.render_user_prompt(
                "review_trend_entry",
                {
                    "as_of": f"{as_of:%Y-%m-%d %H:%M}",
                    "coin": coin,
                    "symbol": symbol,
                    "window_h": self._config.window_h,
                    "coin_headlines": [self._line(i) for i in mentions],
                    "other_headlines": [self._line(i) for i in others],
                },
            )
            runs = await asyncio.gather(
                *(self._agent.run(prompt) for _ in range(self._config.samples))
            )
            samples = [run.output for run in runs]
        vetoes = sum(s.verdict == "VETO" for s in samples)
        # No headlines means no news to act on, so the rule's entry stands.
        decision: Literal["KEEP", "VETO"] = (
            "VETO" if vetoes * 2 > self._config.samples else "KEEP"
        )
        logger.info(
            "Trend gate %s at %s: %s (%d/%d VETO, %d coin + %d other headlines)",
            symbol,
            as_of,
            decision,
            vetoes,
            len(samples),
            len(mentions),
            len(others),
            extra={"symbol": symbol, "decision": decision},
        )
        return TrendGateReviewSchema(
            symbol=symbol,
            as_of=as_of,
            decision=decision,
            samples=samples,
            coin_headlines=len(mentions),
            other_headlines=len(others),
            prompt_sha=self._prompt_sha,
        )

    @staticmethod
    def _line(item: NewsItemSchema) -> str:
        stamp = (
            f"{item.published_at:%Y-%m-%d %H:%M}"
            if item.precision == "exact"
            else f"{item.published_at:%Y-%m-%d} (date only)"
        )
        return f"{stamp} [{item.source}] {item.title}"
