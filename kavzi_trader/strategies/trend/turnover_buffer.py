import numpy as np


class TurnoverBuffer:
    """Holds the previous weight unless a target moves enough to be worth trading."""

    def __init__(self, band: float) -> None:
        if band < 0:
            msg = f"band must be non-negative, got {band}"
            raise ValueError(msg)
        self._band = band

    def apply(self, targets: np.ndarray) -> np.ndarray:
        """Held weights for a (days, symbols) target matrix, starting flat."""
        held = np.zeros_like(targets)
        current = np.zeros(targets.shape[1])
        for t in range(targets.shape[0]):
            current = self.step(targets[t], current)
            held[t] = current
        return held

    def step(self, target: np.ndarray, held: np.ndarray) -> np.ndarray:
        """Weights held after one day, given today's targets and yesterday's holds."""
        trade = self._trade_mask(target, held)
        stepped: np.ndarray = np.where(trade, target, held)
        return stepped

    def _trade_mask(self, target: np.ndarray, held: np.ndarray) -> np.ndarray:
        flatten = (target == 0) & (held != 0)
        flip = np.sign(target) != np.sign(held)
        drift = np.abs(target - held) > self._band * np.abs(held)
        mask: np.ndarray = flatten | flip | drift
        return mask
