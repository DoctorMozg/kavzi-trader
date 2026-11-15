import numpy as np

from kavzi_trader.evals.trend_run_schema import TrendRunSchema


class TrendPortfolio:
    """Turns held weights into daily gross, cost, funding and net returns."""

    def __init__(self, commission_rate: float) -> None:
        if commission_rate < 0:
            msg = f"commission_rate must be non-negative, got {commission_rate}"
            raise ValueError(msg)
        self._commission_rate = commission_rate

    def run(
        self, held: np.ndarray, returns: np.ndarray, funding: np.ndarray
    ) -> TrendRunSchema:
        """All inputs are (days, symbols); funding is the day's summed rate."""
        if not held.shape == returns.shape == funding.shape:
            msg = f"shape mismatch: {held.shape} {returns.shape} {funding.shape}"
            raise ValueError(msg)
        previous = np.vstack([np.zeros(held.shape[1]), held[:-1]])
        traded = np.abs(held - previous).sum(axis=1)
        gross = (held * returns).sum(axis=1)
        cost = self._commission_rate * traded
        # A long pays positive funding, a short receives it.
        paid = (held * funding).sum(axis=1)
        return TrendRunSchema(
            gross=gross, cost=cost, funding=paid, net=gross - cost - paid, traded=traded
        )
