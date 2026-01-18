from enum import Enum


class LiquidityPeriod(str, Enum):
    """Represents market liquidity bands used for size adjustments."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
