from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.distribution_report_schema import DistributionReportSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema


class BuildResultSchema(BaseModel):
    cases: Annotated[list[EvalCaseSchema], Field(...)]
    report: Annotated[DistributionReportSchema, Field(...)]

    model_config = ConfigDict(frozen=True)
