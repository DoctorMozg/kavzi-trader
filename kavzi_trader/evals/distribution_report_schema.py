from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class DistributionReportSchema(BaseModel):
    """Achieved sample mix plus how many candidates each stratum had to offer."""

    selected_by_label: Annotated[dict[str, int], Field(...)]
    selected_by_symbol: Annotated[dict[str, int], Field(...)]
    selected_by_regime: Annotated[dict[str, int], Field(...)]
    selected_by_label_regime: Annotated[dict[str, int], Field(...)]
    selected_by_label_symbol: Annotated[dict[str, int], Field(...)]
    eligible_by_label: Annotated[dict[str, int], Field(...)]
    eligible_by_regime: Annotated[dict[str, int], Field(...)]
    eligible_by_label_regime: Annotated[dict[str, int], Field(...)]
    shortfall_by_label: Annotated[dict[str, int], Field(...)]
    excluded_warmup_or_gap: Annotated[int, Field(...)]
    excluded_geometry_rejected: Annotated[int, Field(...)]

    model_config = ConfigDict(frozen=True)
