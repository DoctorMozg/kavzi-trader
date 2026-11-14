import numpy as np
import pandas as pd

STEP_MS = 900_000
BASE_MS = 1_700_000_000_000 - 1_700_000_000_000 % STEP_MS


def make_frame(
    n: int,
    seed: int = 0,
    start_ms: int = BASE_MS,
    drift_vol: float = 0.002,
    skip: set[int] | None = None,
) -> pd.DataFrame:
    """Random-walk 15m candles; indices in ``skip`` are removed (a data gap)."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, drift_vol, n)))
    open_ = np.concatenate(([100.0], close[:-1]))
    spread = np.abs(rng.normal(0, drift_vol, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    open_time = start_ms + np.arange(n, dtype=np.int64) * STEP_MS
    frame = pd.DataFrame(
        {
            "open_time_ms": open_time,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 10.0,
            "close_time_ms": open_time + STEP_MS - 1,
            "quote_volume": 1000.0,
            "trades_count": 5,
            "taker_buy_base_volume": 5.0,
            "taker_buy_quote_volume": 500.0,
        }
    )
    if skip:
        frame = frame.drop(index=sorted(skip)).reset_index(drop=True)
    return frame
