"""Configuration schemas tuning the ReasoningLoop idle/cooldown cadence.

These values previously lived as module-level constants in
``reasoning.py``. They are extracted into Pydantic schemas so operators
can tune the loop's escalation behaviour (idle-ramp backoff, skip
suspension, WAIT/borderline cooldowns) without editing code and so the
defaults carry inline documentation explaining *why* each threshold
exists.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class IdleRampStairSchema(BaseModel):
    """Single stair in the progressive idle-ramp backoff.

    When the reasoning loop observes ``min_idle_cycles`` consecutive
    cycles with zero INTERESTING scouts, it sleeps ``sleep_s`` seconds
    before the next cycle. Stairs are evaluated in descending order so
    the deepest matching stair wins.
    """

    min_idle_cycles: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "Minimum consecutive idle cycles required for this stair "
                "to activate."
            ),
        ),
    ]
    sleep_s: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "Seconds to sleep between cycles once this stair is the "
                "deepest matching one."
            ),
        ),
    ]

    model_config = ConfigDict(frozen=True)


# Default idle-ramp stair tuple preserved verbatim from the prior
# module-level constant. Ordered descending so the first match is the
# deepest stair. Replaces the doubling backoff which grew continuously
# and masked genuinely idle markets as "slow to wake" rather than
# "truly quiet".
_DEFAULT_IDLE_RAMP_STAIRS: tuple[IdleRampStairSchema, ...] = (
    IdleRampStairSchema(min_idle_cycles=8, sleep_s=720),
    IdleRampStairSchema(min_idle_cycles=5, sleep_s=480),
    IdleRampStairSchema(min_idle_cycles=3, sleep_s=240),
)


class ReasoningLoopConfigSchema(BaseModel):
    """Tunable thresholds for the ReasoningLoop escalation logic.

    Every field documents the behavioural reason the threshold exists
    so future operators can tune safely without re-deriving intent from
    the call sites.
    """

    idle_ramp_stairs: Annotated[
        tuple[IdleRampStairSchema, ...],
        Field(
            description=(
                "Progressive idle-ramp stairs. When N consecutive cycles "
                "observe no INTERESTING scouts, sleep per the deepest "
                "matching stair. Prevents busy-polling genuinely quiet "
                "markets while still waking promptly on activity."
            ),
        ),
    ] = _DEFAULT_IDLE_RAMP_STAIRS

    borderline_cooldown_cycles: Annotated[
        int,
        Field(
            ge=0,
            description=(
                "Cooldown (in cycles) for borderline analyst verdicts and "
                "LLM rejects at high confluence. Short enough that the "
                "next bar-close naturally retriggers the Analyst, long "
                "enough to avoid tight retries within the same bar."
            ),
        ),
    ] = 1

    cooldown_low_confluence_threshold: Annotated[
        int,
        Field(
            ge=0,
            description=(
                "Confluence score at or below which the aggressive "
                "rejection band applies the highest cooldown multiplier. "
                "Scores above this value (but still within the reject "
                "band) use the lower multiplier."
            ),
        ),
    ] = 2

    skip_suspension_threshold: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "Consecutive SKIP verdicts before the symbol is put on "
                "dynamic suspension (evaluated only every Nth cycle). "
                "Prevents burning LLM budget on chronically quiet "
                "symbols."
            ),
        ),
    ] = 20

    max_skip_eval_interval: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "Upper bound (in cycles) on the dynamic skip-evaluation "
                "interval, so a suspended symbol is still re-checked at "
                "least this often."
            ),
        ),
    ] = 16

    wait_cooldown_threshold: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "Consecutive Trader WAIT verdicts before escalating "
                "cooldowns kick in on that (symbol, direction) pair."
            ),
        ),
    ] = 5

    wait_cooldown_base_cycles: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "Base cooldown (in cycles) per excess WAIT past the "
                "threshold. Scales linearly with the excess count up to "
                "wait_max_cooldown_cycles."
            ),
        ),
    ] = 2

    wait_max_cooldown_cycles: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "Maximum cooldown (in cycles) the WAIT-escalation logic "
                "will apply, regardless of how many consecutive WAITs "
                "have accumulated."
            ),
        ),
    ] = 12

    model_config = ConfigDict(frozen=True)
