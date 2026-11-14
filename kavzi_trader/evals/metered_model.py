import logging
import time

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from kavzi_trader.evals.case_meter import CaseMeter, Role
from kavzi_trader.evals.token_usage_schema import TokenUsageSchema

logger = logging.getLogger(__name__)


class MeteredModel(WrapperModel):
    """Reports every request's usage and latency to the active CaseMeter.

    Sits below the agent, so retries and refusals are billed and counted too.
    """

    role: Role

    def __init__(self, wrapped: Model, role: Role) -> None:
        super().__init__(wrapped)
        self.role = role

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        meter = CaseMeter.active()
        start = time.monotonic()
        try:
            response = await super().request(
                messages, model_settings, model_request_parameters
            )
        except Exception as exc:
            if meter is not None:
                meter.record_failure(self.role, self._elapsed_ms(start), exc)
            raise
        if meter is not None:
            usage = response.usage
            meter.record_request(
                self.role,
                self._elapsed_ms(start),
                TokenUsageSchema(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                ),
                refusal=response.finish_reason == "content_filter",
            )
        return response

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return (time.monotonic() - start) * 1000
