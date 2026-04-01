from enum import StrEnum


class TradingMode(StrEnum):
    """Trading mode selection for execution routing."""

    LIVE = "LIVE"
    PAPER = "PAPER"
    DISABLED = "DISABLED"
