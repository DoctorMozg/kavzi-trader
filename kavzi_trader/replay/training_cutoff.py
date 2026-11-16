import pandas as pd

# First day after each model's training-data cutoff (platform.claude.com models
# overview, checked 2026-11-16: Jun 2026 for all three).
CLEAN_FROM_DAY = {
    "claude-opus-5-5": pd.Timestamp("2026-07-01"),
    "claude-sonnet-5-5": pd.Timestamp("2026-07-01"),
    "claude-haiku-5-5": pd.Timestamp("2026-07-01"),
}


def is_contaminated(model_names: list[str], start_ms: int) -> bool:
    """True when any model may have seen the window: it starts before a cutoff.

    A model without a known cutoff counts as having seen everything.
    """
    start = pd.Timestamp(start_ms, unit="ms")
    for name in model_names:
        # OpenRouter names carry a vendor prefix, e.g. anthropic/claude-opus-5-5.
        clean_from = CLEAN_FROM_DAY.get(name.rsplit("/", maxsplit=1)[-1])
        if clean_from is None or start < clean_from:
            return True
    return False
