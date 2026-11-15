from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class FundingXsParamsSchema(BaseModel):
    """Cross-sectional funding rule knobs; defaults are the pre-registered ones."""

    legs: Annotated[int, Field(ge=1)] = 3
    hold_days: Annotated[int, Field(ge=1)] = 3
    cost_rate: Annotated[float, Field(ge=0)] = 0.0005
    score_settlements: Annotated[int, Field(ge=1)] = 9

    model_config = ConfigDict(frozen=True)

    @property
    def leg_weight(self) -> float:
        """Each leg's share of equity: gross 1.0 split over 2 * legs positions."""
        return 1.0 / (2 * self.legs)
