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
            trade = self._trade_mask(targets[t], current)
            current = np.where(trade, targets[t], current)
            held[t] = current
        return held

    def _trade_mask(self, target: np.ndarray, held: np.ndarray) -> np.ndarray:
        flatten = (target == 0) & (held != 0)
        flip = np.sign(target) != np.sign(held)
        drift = np.abs(target - held) > self._band * np.abs(held)
        mask: np.ndarray = flatten | flip | drift
        return mask
