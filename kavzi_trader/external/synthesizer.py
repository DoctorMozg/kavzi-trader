import logging
from datetime import UTC, datetime
from decimal import Decimal

from pydantic_ai import Agent

from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.external.schemas import (
    ExternalDataSnapshotSchema,
    SentimentSummarySchema,
)

logger = logging.getLogger(__name__)

_NEUTRAL_SUMMARY = SentimentSummarySchema(
    summary="No external data available. Treating sentiment as neutral.",
    sentiment_bias="NEUTRAL",
    confidence_adjustment=Decimal(0),
    generated_at=datetime.now(UTC),
)


def _format_snapshot_for_prompt(
    snapshot: ExternalDataSnapshotSchema,
) -> str:
    """Render raw external data as structured text for the synthesizer prompt."""
    parts: list[str] = []

    if snapshot.deribit_dvol is not None:
        d = snapshot.deribit_dvol
        parts.append(
            f"DERIBIT OPTIONS:\n"
            f"  DVOL (30-day implied volatility): {float(d.dvol_index):.1f}\n"
            f"  BTC Put/Call OI Ratio: {float(d.btc_put_call_ratio):.3f}"
        )
    else:
        parts.append("DERIBIT OPTIONS: unavailable")

    if snapshot.fear_greed is not None:
        fg = snapshot.fear_greed
        parts.append(
            f"FEAR & GREED INDEX:\n  Value: {fg.value}/100 ({fg.classification})"
        )
    else:
        parts.append("FEAR & GREED INDEX: unavailable")

    if snapshot.cryptopanic is not None:
        cp = snapshot.cryptopanic
        headlines_text = ""
        if cp.top_headlines:
            headlines_text = "\n  Headlines:\n" + "\n".join(
                f"    - {h}" for h in cp.top_headlines[:10]
            )
        parts.append(
            f"NEWS SENTIMENT (CryptoPanic):\n"
            f"  Bullish: {cp.bullish_count}, Bearish: {cp.bearish_count},"
            f" Neutral: {cp.neutral_count}\n"
            f"  Aggregate score: {float(cp.sentiment_score):+.2f}"
            f" (-1=bearish, +1=bullish)"
            f"{headlines_text}"
        )
    else:
        parts.append("NEWS SENTIMENT: unavailable")

    return "\n\n".join(parts)


class SentimentSynthesizer:
    """Cheap LLM agent that pre-digests raw external data into a compact summary.

    Called by ExternalSentimentLoop after each fetch cycle.
    Uses a cheap model (e.g. deepseek) via OpenRouter to save tokens.
    """

    def __init__(
        self,
        agent: Agent[None, SentimentSummarySchema],
        prompt_loader: PromptLoader,
    ) -> None:
        self._agent = agent
        self._prompt_loader = prompt_loader

    async def synthesize(
        self,
        snapshot: ExternalDataSnapshotSchema,
    ) -> SentimentSummarySchema | None:
        if snapshot.is_empty():
            logger.debug("Empty snapshot, returning neutral summary")
            return SentimentSummarySchema(
                summary="No external data available. Treating sentiment as neutral.",
                sentiment_bias="NEUTRAL",
                confidence_adjustment=Decimal(0),
                generated_at=datetime.now(UTC),
            )

        try:
            user_prompt = self._prompt_loader.render_user_prompt(
                "synthesize_sentiment",
                {"external_data_block": _format_snapshot_for_prompt(snapshot)},
            )
            result = await self._agent.run(user_prompt)
        except Exception:
            logger.exception("Sentiment synthesis LLM call failed")
            return None
        else:
            output: SentimentSummarySchema = result.output
            logger.info(
                "Sentiment synthesized: bias=%s adjustment=%s",
                output.sentiment_bias,
                output.confidence_adjustment,
            )
            return output
