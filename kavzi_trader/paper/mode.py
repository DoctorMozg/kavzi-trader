from enum import Enum


class TradingMode(str, Enum):
    """Trading mode selection for execution routing."""

    LIVE = "LIVE"
    TESTNET = "TESTNET"
    PAPER = "PAPER"
    DISABLED = "DISABLED"
