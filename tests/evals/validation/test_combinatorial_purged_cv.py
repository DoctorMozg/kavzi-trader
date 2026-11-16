import numpy as np
import pytest

from kavzi_trader.evals.validation.combinatorial_purged_cv import (
    CombinatorialPurgedCV,
)


class TestSplitsAndPaths:
    def test_six_groups_two_tested_give_15_splits_and_5_paths(self) -> None:
        cv = CombinatorialPurgedCV(6, 2)

        assert len(cv.split(60)) == 15
        assert cv.n_paths == 5
        assert cv.paths().shape == (5, 6)

    def test_each_path_tests_every_group_once_from_a_split_that_tested_it(
        self,
    ) -> None:
        cv = CombinatorialPurgedCV(6, 2)
        splits = cv.split(60)

        for path in cv.paths():
            for group, split_index in enumerate(path):
                assert group in splits[split_index].test_groups

    def test_without_purge_train_and_test_partition_the_data(self) -> None:
        for split in CombinatorialPurgedCV(5, 2).split(53):
            both = np.concatenate([split.train, split.test])
            assert np.array_equal(np.sort(both), np.arange(53))


class TestPurgeAndEmbargo:
    def test_overlapping_labels_and_the_embargo_leave_training(self) -> None:
        cv = CombinatorialPurgedCV(6, 1, label_horizon=2, embargo=3)

        [split] = [s for s in cv.split(60) if s.test_groups == [2]]

        # Test is 20..29: 18-19 reach into it, 30-31 start inside its labels,
        # 32-34 are the embargo.
        expected = np.concatenate([np.arange(0, 18), np.arange(35, 60)])
        assert np.array_equal(split.train, expected)

    def test_adjacent_tested_groups_purge_as_one_block(self) -> None:
        cv = CombinatorialPurgedCV(6, 2, label_horizon=1)

        [split] = [s for s in cv.split(60) if s.test_groups == [2, 3]]

        expected = np.concatenate([np.arange(0, 19), np.arange(41, 60)])
        assert np.array_equal(split.train, expected)

    def test_test_group_count_must_leave_training_groups(self) -> None:
        with pytest.raises(ValueError, match="n_test_groups"):
            CombinatorialPurgedCV(4, 4)
