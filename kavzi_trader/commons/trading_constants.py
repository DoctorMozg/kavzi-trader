from decimal import Decimal

MIN_RR_RATIO = Decimal("2.0")

# Distance (in ATR multiples) a stop loss is placed beyond its anchoring
# key level, so the stop survives a liquidity sweep of the level itself.
SL_LEVEL_BUFFER_ATR = Decimal("0.1")

# Realistic take-profit ceiling in ATR multiples. Matches the deepest
# target the Analyst projects (3.0x ATR); geometry that needs a further
# target to reach MIN_RR_RATIO is rejected rather than stretched into
# territory the setup cannot plausibly reach within the hold horizon.
MAX_TP_ATR = Decimal("3.0")
