from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from kavzi_trader.replay.llm_tape import LlmTape
from kavzi_trader.replay.replay_model import ReplayModel, TapeMissError


class DecisionSchema(BaseModel):
    action: str


class Provider:
    """A scripted model: its first answer is rejected, the second accepted."""

    def __init__(self) -> None:
        self.calls = 0

    def answer(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.calls += 1
        action = "MAYBE" if self.calls % 2 else "WAIT"
        tool = info.output_tools[0].name
        return ModelResponse(
            parts=[ToolCallPart(tool_name=tool, args={"action": action})]
        )


def _agent(model: ReplayModel) -> Agent[None, DecisionSchema]:
    agent = Agent(model, output_type=DecisionSchema, instructions="Decide.")

    @agent.output_validator
    def _known(output: DecisionSchema) -> DecisionSchema:
        if output.action not in {"WAIT", "LONG"}:
            raise ModelRetry("action must be WAIT or LONG")
        return output

    return agent


@pytest.fixture
def provider() -> Provider:
    return Provider()


@pytest.fixture
def tape_path(tmp_path: Path) -> Path:
    return tmp_path / "tape.jsonl"


async def _record(provider: Provider, tape_path: Path) -> DecisionSchema:
    model = ReplayModel(FunctionModel(provider.answer), LlmTape(tape_path), record=True)
    return (await _agent(model).run("BTCUSDT at 100")).output


async def test_replay_from_disk_answers_without_the_provider(
    provider: Provider, tape_path: Path
) -> None:
    recorded = await _record(provider, tape_path)
    assert provider.calls == 2  # the retry put the first response into history

    replay = ReplayModel(
        FunctionModel(provider.answer), LlmTape(tape_path), record=False
    )
    replayed = (await _agent(replay).run("BTCUSDT at 100")).output

    assert replayed == recorded
    assert provider.calls == 2
    assert replay.provider_calls == 0


async def test_replay_only_run_refuses_an_unseen_request(
    provider: Provider, tape_path: Path
) -> None:
    await _record(provider, tape_path)
    replay = ReplayModel(
        FunctionModel(provider.answer), LlmTape(tape_path), record=False
    )

    with pytest.raises(TapeMissError):
        await _agent(replay).run("ETHUSDT at 100")
    assert provider.calls == 2


async def test_recording_again_reuses_the_tape(
    provider: Provider, tape_path: Path
) -> None:
    await _record(provider, tape_path)

    await _record(provider, tape_path)

    assert provider.calls == 2
    assert len(LlmTape(tape_path)) == 2
