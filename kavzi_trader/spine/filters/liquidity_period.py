from enum import StrEnum


class LiquidityPeriod(StrEnum):
    """Represents market liquidity bands used for size adjustments."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
