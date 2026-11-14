import asyncio

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from kavzi_trader.evals.case_meter import CaseMeter
from kavzi_trader.evals.cost_calculator import CostCalculator
from kavzi_trader.evals.metered_model import MeteredModel


class Answer(BaseModel):
    value: int


def _agent(reply: ModelResponse | Exception) -> Agent[None, Answer]:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if isinstance(reply, Exception):
            raise reply
        return reply

    model = FunctionModel(respond, model_name="claude-sonnet-5-5")
    agent = Agent(model, output_type=NativeOutput(Answer))
    agent.model = MeteredModel(model, "analyst")
    return agent


class TestMeteredModel:
    async def test_usage_including_cache_tokens_is_recorded(self) -> None:
        reply = ModelResponse(
            parts=[TextPart('{"value": 1}')],
            usage=RequestUsage(
                input_tokens=1000,
                output_tokens=50,
                cache_read_tokens=600,
                cache_write_tokens=200,
            ),
        )
        meter = CaseMeter()

        with meter:
            await _agent(reply).run("go")
        metrics = meter.metrics("analyst", "claude-sonnet-5-5", CostCalculator())

        assert metrics.requests == 1
        assert metrics.usage.input_tokens == 1000
        assert metrics.usage.cache_read_tokens == 600
        assert metrics.usage.cache_write_tokens == 200
        assert metrics.cost_usd is not None
        assert metrics.cost_usd > 0
        assert metrics.error is None

    async def test_transport_error_is_recorded_and_still_raised(self) -> None:
        meter = CaseMeter()

        with meter:
            try:
                await _agent(TimeoutError("slow")).run("go")
            except TimeoutError:
                pass
            else:
                raise AssertionError("TimeoutError should propagate")

        error = meter.metrics("analyst", "x", CostCalculator()).error
        assert error == "TimeoutError: slow"

    async def test_meters_of_concurrent_cases_stay_separate(self) -> None:
        reply = ModelResponse(
            parts=[TextPart('{"value": 1}')],
            usage=RequestUsage(input_tokens=10, output_tokens=1),
        )
        agent = _agent(reply)
        first, second = CaseMeter(), CaseMeter()

        async def run(meter: CaseMeter, times: int) -> None:
            with meter:
                for _ in range(times):
                    await agent.run("go")

        await asyncio.gather(run(first, 1), run(second, 3))

        costs = CostCalculator()
        assert first.metrics("analyst", "m", costs).requests == 1
        assert second.metrics("analyst", "m", costs).requests == 3
