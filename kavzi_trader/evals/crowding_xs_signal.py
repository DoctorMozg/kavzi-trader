import numpy as np
import pandas as pd

_MIN_LEG = 3


class CrowdingXsSignal:
    """Dollar-neutral ls_crowding book: short the most crowded third, long the least.

    Every ``rebalance_days`` from ``anchor`` the symbols with a rank and a close are
    sorted; each leg holds ``fraction`` of them at equal weight, 0.5 gross per leg.
    Weights stay fixed until the next rebalance. Fewer than three names a leg: flat.
    """

    def __init__(
        self,
        ranks: pd.DataFrame,
        anchor: pd.Timestamp,
        rebalance_days: int = 7,
        fraction: float = 1 / 3,
    ) -> None:
        self._ranks = ranks
        self._anchor = anchor
        self._every = rebalance_days
        self._fraction = fraction

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        ranks = self._ranks.reindex(index=closes.index, columns=closes.columns)
        target = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
        offsets = (closes.index - self._anchor).days
        for day in closes.index[(offsets >= 0) & (offsets % self._every == 0)]:
            target.loc[day] = self.book(ranks.loc[day].where(closes.loc[day].notna()))
        held: np.ndarray = target.ffill().fillna(0.0).to_numpy()
        return held

    def book(self, ranks: pd.Series) -> pd.Series:
        """Weights for one rebalance from that day's ranks (NaN: not eligible)."""
        known = ranks.dropna().sort_values(kind="stable")
        leg = int(len(known) * self._fraction)
        weights = pd.Series(0.0, index=ranks.index)
        if leg < _MIN_LEG:
            return weights
        weights[known.index[:leg]] = 0.5 / leg
        weights[known.index[-leg:]] = -0.5 / leg
        return weights
