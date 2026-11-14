from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kavzi_trader.domain.volatility_regime import VolatilityRegime


class ValidationOutcomeSchema(BaseModel):
    """Result of a single pre-execution validator.

    Validators fan out from `ExecutionEngine.execute()` and each returns one of
    these. A failing outcome short-circuits the pipeline and populates the
    rejection `ExecutionResultSchema`; a passing outcome may still carry
    the stricter volatility regime chosen by the drift check.
    """

    passed: Annotated[bool, Field(...)]
    reason: Annotated[str | None, Field(default=None)]
    effective_regime: Annotated[VolatilityRegime | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def require_reason_when_failed(self) -> ValidationOutcomeSchema:
        if not self.passed and not self.reason:
            raise ValueError("reason is required when passed is False")
        return self
