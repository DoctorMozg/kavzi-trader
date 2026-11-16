import logging

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from kavzi_trader.replay.llm_tape import LlmTape

logger = logging.getLogger(__name__)


class TapeMissError(RuntimeError):
    """A replay-only run met a request the tape has no response for."""


class ReplayModel(WrapperModel):
    """Answers from the tape; on a miss calls the wrapped model only when recording.

    Only ``request`` is taped: the agents never stream.
    """

    def __init__(self, wrapped: Model, tape: LlmTape, *, record: bool) -> None:
        super().__init__(wrapped)
        self._tape = tape
        self._record = record
        self.provider_calls = 0

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        key = LlmTape.key(
            self.model_name, messages, model_settings, model_request_parameters
        )
        taped = self._tape.get(key)
        if taped is not None:
            return taped
        if not self._record:
            msg = f"no taped response for {self.model_name} request {key[:12]}"
            raise TapeMissError(msg)
        logger.debug("Tape miss for %s, calling the provider", self.model_name)
        self.provider_calls += 1
        response = await super().request(
            messages, model_settings, model_request_parameters
        )
        self._tape.put(key, response)
        return response
