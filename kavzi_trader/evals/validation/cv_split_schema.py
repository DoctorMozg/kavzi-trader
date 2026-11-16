import numpy as np
from pydantic import BaseModel, ConfigDict


class CvSplitSchema(BaseModel):
    """One train/test split: observation indices, purged and embargoed."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    train: np.ndarray
    test: np.ndarray
    test_groups: list[int]
