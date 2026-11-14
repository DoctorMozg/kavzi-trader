from typing import TypedDict


class ConfluenceBlockDict(TypedDict):
    """Serialized shape of ``AlgorithmConfluenceSchema.model_dump()``.

    Produced by callers that dump a single side of
    ``DualConfluenceSchema`` and then pass both sides through
    :func:`side_trim_confluence` before handing the result to the Brain.
    Jinja templates read these fields directly (see
    ``user/context/algorithm_confluence.j2``).
    """

    ema_alignment: bool
    rsi_favorable: bool
    volume_above_average: bool
    price_at_bollinger: bool
    funding_favorable: bool
    oi_supports_direction: bool
    oi_funding_divergence: bool
    volume_spike: bool
    score: int


def side_trim_confluence(
    dual_long: ConfluenceBlockDict,
    dual_short: ConfluenceBlockDict,
    detected_side: str,
) -> tuple[ConfluenceBlockDict | None, ConfluenceBlockDict | None]:
    """Return (long, short) dicts trimmed to the detected side.

    When ``detected_side`` is LONG or SHORT, the opposing block is
    dropped so the LLM only sees the perspective it will act on. When
    the confluence is NEUTRAL, both sides remain so the LLM can
    compare. Saves ~300 prompt tokens per trending request.
    """
    if detected_side == "LONG":
        return dual_long, None
    if detected_side == "SHORT":
        return None, dual_short
    return dual_long, dual_short
