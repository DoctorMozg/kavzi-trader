import logging
from itertools import combinations

import numpy as np
import pandas as pd

from kavzi_trader.evals.validation.pbo_schema import PboSchema

logger = logging.getLogger(__name__)


class BacktestOverfitting:
    """PBO via CSCV (Bailey, Borwein, Lopez de Prado & Zhu, 2015), Sharpe-ranked."""

    def __init__(self, n_blocks: int = 16) -> None:
        if n_blocks < 2 or n_blocks % 2:  # noqa: PLR2004 - CSCV needs an even S >= 2
            msg = f"n_blocks must be even and at least 2, got {n_blocks}"
            raise ValueError(msg)
        self._n_blocks = n_blocks

    def probability(self, returns: np.ndarray) -> PboSchema:
        """``returns`` is (periods, trials): one column of returns per variant."""
        if returns.ndim != 2 or returns.shape[1] < 2:  # noqa: PLR2004
            msg = f"need a 2-D matrix of at least 2 trials, got {returns.shape}"
            raise ValueError(msg)
        n_blocks = self._n_blocks
        rows = returns.shape[0] - returns.shape[0] % n_blocks
        if rows < 2 * n_blocks:
            msg = f"{returns.shape[0]} periods are too few for {n_blocks} blocks"
            raise ValueError(msg)
        if rows < returns.shape[0]:
            logger.info("PBO drops the %d oldest periods", returns.shape[0] - rows)
        blocks = returns[-rows:].reshape(n_blocks, rows // n_blocks, -1)
        # Per-block sums let each half's Sharpe come from block totals.
        sums = blocks.sum(axis=1)
        squares = (blocks**2).sum(axis=1)
        size = rows // n_blocks * (n_blocks // 2)
        n_trials = returns.shape[1]
        logits = []
        for chosen in combinations(range(n_blocks), n_blocks // 2):
            train = np.zeros(n_blocks, dtype=bool)
            train[list(chosen)] = True
            best = int(np.argmax(_sharpe(sums[train], squares[train], size)))
            test = _sharpe(sums[~train], squares[~train], size)
            # Rank 1 is the worst trial; ties share their average rank.
            rank = float(pd.Series(test).rank(method="average").iloc[best])
            omega = rank / (n_trials + 1)
            logits.append(float(np.log(omega / (1 - omega))))
        pbo = float(np.mean(np.array(logits) <= 0))
        logger.info("PBO %.3f over %d CSCV splits", pbo, len(logits))
        return PboSchema(pbo=pbo, n_combinations=len(logits), logits=logits)


def _sharpe(sums: np.ndarray, squares: np.ndarray, size: int) -> np.ndarray:
    total = sums.sum(axis=0)
    mean = total / size
    variance = (squares.sum(axis=0) - size * mean**2) / (size - 1)
    std = np.sqrt(np.maximum(variance, 0))
    # A flat trial has no Sharpe; rank it below every trial that moved.
    return np.where(std > 0, mean / np.where(std > 0, std, 1), -np.inf)
