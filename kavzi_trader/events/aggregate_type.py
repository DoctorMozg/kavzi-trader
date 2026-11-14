from enum import StrEnum


class AggregateType(StrEnum):
    """Event stream owners; values double as the keys of the stream config."""

    ORDERS = "orders"
    POSITIONS = "positions"
    DECISIONS = "decisions"
    SYSTEM = "system"
    LIQUIDATIONS = "liquidations"


class UnknownAggregateTypeError(ValueError):
    """Raised when an event's aggregate type has no configured stream."""
