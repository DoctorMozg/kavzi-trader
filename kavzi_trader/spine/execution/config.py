from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.spine.risk.schemas import VolatilityRegime


def _default_staleness_thresholds() -> dict[str, int]:
    return {
        VolatilityRegime.LOW.value: 300_000,
        VolatilityRegime.NORMAL.value: 120_000,
        VolatilityRegime.HIGH.value: 90_000,
        VolatilityRegime.EXTREME.value: 30_000,
    }


class ExecutionConfigSchema(BaseModel):
    """Execution engine runtime configuration."""

    timeout_s: Annotated[int, Field(ge=1)] = 30
    max_retry_attempts: Annotated[int, Field(ge=0)] = 3
    immediate_sl_tp: Annotated[bool, Field()] = True
    staleness_thresholds_ms: Annotated[dict[str, int], Field()] = Field(
        default_factory=_default_staleness_thresholds,
    )

    model_config = ConfigDict(frozen=True)
