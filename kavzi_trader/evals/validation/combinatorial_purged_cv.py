import logging
from itertools import combinations
from math import comb

import numpy as np

from kavzi_trader.evals.validation.cv_split_schema import CvSplitSchema

logger = logging.getLogger(__name__)


class CombinatorialPurgedCV:
    """CPCV (Lopez de Prado, AFML ch. 12) over time-ordered observations.

    Observation i's label spans bars [i, i + label_horizon]. A training
    observation whose label overlaps a test label is purged, and the
    ``embargo`` bars after each test block are dropped too.
    """

    def __init__(
        self,
        n_groups: int,
        n_test_groups: int,
        label_horizon: int = 0,
        embargo: int = 0,
    ) -> None:
        if not 0 < n_test_groups < n_groups:
            msg = f"need 0 < n_test_groups < n_groups, got {n_test_groups}/{n_groups}"
            raise ValueError(msg)
        if label_horizon < 0 or embargo < 0:
            msg = f"bad label_horizon {label_horizon} or embargo {embargo}"
            raise ValueError(msg)
        self._n_groups = n_groups
        self._k = n_test_groups
        self._horizon = label_horizon
        self._embargo = embargo

    @property
    def n_paths(self) -> int:
        """Full out-of-sample paths: each group is tested C(N-1, k-1) times."""
        return comb(self._n_groups - 1, self._k - 1)

    def split(self, n_obs: int) -> list[CvSplitSchema]:
        if n_obs < self._n_groups:
            msg = f"{n_obs} observations cannot fill {self._n_groups} groups"
            raise ValueError(msg)
        groups = np.array_split(np.arange(n_obs), self._n_groups)
        splits = []
        for tested in combinations(range(self._n_groups), self._k):
            test = np.concatenate([groups[g] for g in tested])
            keep = np.ones(n_obs, dtype=bool)
            keep[test] = False
            for start, end in _blocks(groups, tested):
                # Labels [i, i + h] and [j, j + h] overlap when |i - j| <= h.
                low = max(start - self._horizon, 0)
                keep[low : end + self._horizon + self._embargo + 1] = False
            splits.append(
                CvSplitSchema(
                    train=np.flatnonzero(keep), test=test, test_groups=list(tested)
                )
            )
        logger.info(
            "CPCV: %d splits, %d paths over %d observations",
            len(splits),
            self.n_paths,
            n_obs,
        )
        return splits

    def paths(self) -> np.ndarray:
        """(n_paths, n_groups): which split supplies each group's test returns.

        Path p takes, for every group, the p-th split that tested it.
        """
        testers: list[list[int]] = [[] for _ in range(self._n_groups)]
        tested_sets = combinations(range(self._n_groups), self._k)
        for split_index, tested in enumerate(tested_sets):
            for group in tested:
                testers[group].append(split_index)
        return np.array(testers).T


def _blocks(groups: list[np.ndarray], tested: tuple[int, ...]) -> list[list[int]]:
    """First and last index of each run of adjacent tested groups."""
    runs: list[list[int]] = []
    previous = None
    for g in tested:
        if previous is not None and g == previous + 1:
            runs[-1][1] = int(groups[g][-1])
        else:
            runs.append([int(groups[g][0]), int(groups[g][-1])])
        previous = g
    return runs
