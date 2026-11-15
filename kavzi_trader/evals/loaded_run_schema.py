from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.case_result_schema import CaseResultSchema
from kavzi_trader.evals.joined_case_schema import JoinedCaseSchema
from kavzi_trader.evals.run_header_schema import RunHeaderSchema


class LoadedRunSchema(BaseModel):
    """A run with its header; scored cases are joined, errored ones are kept apart."""

    header: Annotated[RunHeaderSchema, Field(...)]
    results: Annotated[list[CaseResultSchema], Field(...)]
    scored: Annotated[list[JoinedCaseSchema], Field(...)]

    model_config = ConfigDict(frozen=True)

    @property
    def errored(self) -> list[CaseResultSchema]:
        return [r for r in self.results if r.status == "error"]
