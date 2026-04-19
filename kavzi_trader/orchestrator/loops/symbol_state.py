"""Per-symbol state tracking for the ReasoningLoop.

Collapses the five parallel per-symbol tracking dicts (cooldowns,
consecutive rejections/waits/skips, skip-eval interval) that previously
lived on ``ReasoningLoop`` into a single cohesive state object. Keeping
the state in one place prevents drift between the dicts (e.g. clearing
``_consecutive_rejections`` without resetting ``_cooldowns``) and gives
call sites a typed API rather than raw ``dict[tuple[str, str], int]``
indexing.

Two directional fields (``cooldown_cycles``, ``consecutive_rejections``,
``consecutive_waits``) are stored as ``dict[str, int]`` keyed by
direction string (``"LONG"`` / ``"SHORT"``). The remaining two fields
are scalar per-symbol counters.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class SymbolStateSchema(BaseModel):
    """Mutable per-symbol reasoning state.

    Holds every counter the ReasoningLoop previously spread across five
    parallel dicts. Mutable because the loop bumps/decrements these
    counters every cycle; wrapping each mutation in ``model_copy`` would
    add allocation cost with no safety benefit for a private in-process
    counter.
    """

    cooldown_cycles: Annotated[
        dict[str, int],
        Field(
            default_factory=dict,
            description=(
                "Remaining cooldown cycles per direction ('LONG' / 'SHORT'). "
                "When > 0 the ReasoningLoop skips running the pipeline for "
                "that (symbol, direction) pair."
            ),
        ),
    ]
    consecutive_rejections: Annotated[
        dict[str, int],
        Field(
            default_factory=dict,
            description=(
                "Consecutive Analyst rejection count per direction. Drives "
                "the escalating rejection-cooldown multiplier."
            ),
        ),
    ]
    consecutive_waits: Annotated[
        dict[str, int],
        Field(
            default_factory=dict,
            description=(
                "Consecutive Trader WAIT count per direction. Drives the "
                "WAIT-escalation cooldown once the threshold is crossed."
            ),
        ),
    ]
    consecutive_skips: Annotated[
        int,
        Field(
            ge=0,
            default=0,
            description=(
                "Consecutive Scout SKIP verdicts across all directions for "
                "this symbol. Drives dynamic skip-suspension."
            ),
        ),
    ]
    skip_eval_interval: Annotated[
        int,
        Field(
            ge=0,
            default=0,
            description=(
                "Current dynamic skip-evaluation interval (in cycles) for "
                "this symbol. 0 means 'not suspended'."
            ),
        ),
    ]

    model_config = ConfigDict(frozen=False)


class SymbolStateTracker:
    """Owns and mutates ``SymbolStateSchema`` entries keyed by symbol.

    Exposes narrow methods matching the mutation patterns in
    ``ReasoningLoop`` so call sites avoid re-implementing get-or-create
    logic. Default entries are lazily materialised on first access.
    """

    def __init__(self) -> None:
        self._states: dict[str, SymbolStateSchema] = {}

    def get(self, symbol: str) -> SymbolStateSchema:
        """Return the existing state for ``symbol``, creating defaults."""
        state = self._states.get(symbol)
        if state is None:
            state = SymbolStateSchema.model_validate({})
            self._states[symbol] = state
        return state

    # --- cooldown (per direction) -----------------------------------------
    def cooldown(self, symbol: str, direction: str) -> int:
        return self.get(symbol).cooldown_cycles.get(direction, 0)

    def set_cooldown(self, symbol: str, direction: str, cycles: int) -> None:
        self.get(symbol).cooldown_cycles[direction] = cycles

    def decrement_cooldown(self, symbol: str, direction: str) -> None:
        """Decrement the cooldown by one cycle if it is positive."""
        state = self.get(symbol)
        current = state.cooldown_cycles.get(direction, 0)
        if current > 0:
            state.cooldown_cycles[direction] = current - 1

    # --- consecutive rejections (per direction) ---------------------------
    def consecutive_rejections(self, symbol: str, direction: str) -> int:
        return self.get(symbol).consecutive_rejections.get(direction, 0)

    def bump_rejection(self, symbol: str, direction: str) -> int:
        state = self.get(symbol)
        count = state.consecutive_rejections.get(direction, 0) + 1
        state.consecutive_rejections[direction] = count
        return count

    def clear_rejections(self, symbol: str, direction: str) -> None:
        self.get(symbol).consecutive_rejections.pop(direction, None)

    # --- consecutive waits (per direction) --------------------------------
    def consecutive_waits(self, symbol: str, direction: str) -> int:
        return self.get(symbol).consecutive_waits.get(direction, 0)

    def bump_wait(self, symbol: str, direction: str) -> int:
        state = self.get(symbol)
        count = state.consecutive_waits.get(direction, 0) + 1
        state.consecutive_waits[direction] = count
        return count

    def clear_waits(self, symbol: str, direction: str) -> None:
        self.get(symbol).consecutive_waits.pop(direction, None)

    # --- consecutive skips + skip-eval interval (per symbol) --------------
    def consecutive_skips(self, symbol: str) -> int:
        return self.get(symbol).consecutive_skips

    def skip_eval_interval(self, symbol: str) -> int:
        return self.get(symbol).skip_eval_interval

    def bump_skip(self, symbol: str) -> int:
        state = self.get(symbol)
        state.consecutive_skips += 1
        return state.consecutive_skips

    def set_skip_eval_interval(self, symbol: str, interval: int) -> None:
        self.get(symbol).skip_eval_interval = interval

    def clear_skip_suspension(self, symbol: str) -> None:
        """Reset both skip counters (called on any non-SKIP scout verdict)."""
        state = self.get(symbol)
        state.consecutive_skips = 0
        state.skip_eval_interval = 0
