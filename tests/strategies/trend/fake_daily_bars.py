import numpy as np


class FakeDailyBars:
    """Serves the closes up to a day index the test moves forward."""

    def __init__(self, closes: dict[str, np.ndarray]) -> None:
        self._closes = closes
        self.upto = 0
        self.calls = 0

    async def closes(self, symbol: str, days: int, now_ms: int) -> np.ndarray:
        self.calls += 1
        return self._closes[symbol][: self.upto + 1][-days:]
