from enum import IntEnum, StrEnum


class CaseLabel(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class BarrierOutcome(StrEnum):
    TP = "tp"
    SL = "sl"
    TIMEOUT = "timeout"


class OutcomeCode(IntEnum):
    """Integer codes used inside the vectorised walk; mapped to BarrierOutcome."""

    TP = 0
    SL = 1
    TIMEOUT = 2
