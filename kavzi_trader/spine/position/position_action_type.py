from enum import Enum


class PositionActionType(str, Enum):
    """Names the kind of change to apply to an open position."""

    NO_ACTION = "NO_ACTION"
    MOVE_STOP_LOSS = "MOVE_STOP_LOSS"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    FULL_EXIT = "FULL_EXIT"
    SCALE_IN = "SCALE_IN"
