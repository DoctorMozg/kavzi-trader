from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RouterConfigSchema(BaseModel):
    """Thresholds for deterministic pre-Trader gates and log truncation.

    Extracted from module-level constants so tests and backtests can vary the
    gates without monkey-patching the router module.
    """

    breakout_overextended_b_long: Annotated[
        Decimal,
        Field(
            description=(
                "Reject BREAKOUT longs when Bollinger %B exceeds this "
                "overextension ceiling. Beyond the upper band price has "
                "already stretched past the volatility envelope; chasing "
                "entries here statistically mean-reverts before the "
                "intended target, so these setups are refused outright."
            ),
        ),
    ] = Decimal("1.20")

    breakout_overextended_b_short: Annotated[
        Decimal,
        Field(
            description=(
                "Reject BREAKOUT shorts when Bollinger %B falls below "
                "this overextension floor. Symmetric to the long ceiling: "
                "price has punched well below the lower band and the "
                "short-side edge has been consumed, so further shorts "
                "are refused to avoid selling the bottom of the move."
            ),
        ),
    ] = Decimal("-0.20")

    rr_min_prescreen: Annotated[
        Decimal,
        Field(
            description=(
                "Warn when estimated R/R falls below this pre-screen "
                "threshold but still forward the setup to the Trader "
                "LLM. The Analyst's key-level geometry can "
                "under-represent reward, so we let the Trader make the "
                "final call with full context."
            ),
        ),
    ] = Decimal("1.2")

    rr_hard_block: Annotated[
        Decimal,
        Field(
            description=(
                "Skip the Trader LLM entirely when estimated R/R is "
                "below this floor. Geometry is statistically guaranteed "
                "to lose at current TP-hit rates, so the call is "
                "elided to conserve budget (see "
                "reports/report_2026_04_10.md recommendation #6)."
            ),
        ),
    ] = Decimal("0.5")

    body_preview_chars: Annotated[
        int,
        Field(
            description=(
                "Truncate raw model response bodies after this many "
                "characters when inlined into a log message. Keeps the "
                "human-readable log line bounded while the full body is "
                "still attached via extra['raw_body'] for JSONL "
                "consumers that can handle arbitrary sizes."
            ),
        ),
    ] = 500

    exc_message_preview_chars: Annotated[
        int,
        Field(
            description=(
                "Truncate generic exception str() output after this "
                "many characters when inlined into a log message. "
                "Prevents verbose HTTP error bodies from flooding the "
                "log stream; full exception is still captured via "
                "logger.exception tracebacks."
            ),
        ),
    ] = 200

    model_config = ConfigDict(frozen=True)
