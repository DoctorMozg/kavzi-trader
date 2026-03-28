import asyncio
import logging
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent

from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.external.schemas import (
    ExternalDataSnapshotSchema,
    SentimentSummarySchema,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_S = 2.0


class _SynthesizerOutputSchema(BaseModel):
    """Simplified output schema for the LLM agent.

    Uses float instead of Decimal and omits generated_at so the tool
    JSON schema stays compatible with all providers (e.g. DeepSeek).
    """

    summary: Annotated[
        str,
        Field(..., description="Compact LLM-generated analysis, ~2-3 sentences"),
    ]
    sentiment_bias: Annotated[
        Literal["BULLISH", "BEARISH", "NEUTRAL"],
        Field(...),
    ]
    confidence_adjustment: Annotated[
        float,
        Field(
            ...,
            ge=-0.10,
            le=0.10,
            description="Suggested confidence adjustment for analyst/trader",
        ),
    ]

    model_config = ConfigDict(frozen=True)


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
        agent: Agent[None, _SynthesizerOutputSchema],
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
            )

        user_prompt = self._prompt_loader.render_user_prompt(
            "synthesize_sentiment",
            {"external_data_block": _format_snapshot_for_prompt(snapshot)},
        )

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                result = await self._agent.run(user_prompt)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "Sentiment synthesis attempt %d/%d failed: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_BACKOFF_S * (attempt + 1))
                continue

            output = result.output
            summary = SentimentSummarySchema(
                summary=output.summary,
                sentiment_bias=output.sentiment_bias,
                confidence_adjustment=Decimal(str(output.confidence_adjustment)),
            )
            logger.info(
                "Sentiment synthesized: bias=%s adjustment=%s summary=%s",
                summary.sentiment_bias,
                summary.confidence_adjustment,
                summary.summary,
            )
            return summary

        logger.exception(
            "Sentiment synthesis failed after %d attempts",
            _MAX_RETRIES,
            exc_info=last_error,
        )
        return None
