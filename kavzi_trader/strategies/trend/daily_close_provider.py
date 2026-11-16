from typing import Protocol

import numpy as np


class DailyCloseProvider(Protocol):
    """Supplies closed daily closes, oldest first."""

    async def closes(self, symbol: str, days: int, now_ms: int) -> np.ndarray: ...
