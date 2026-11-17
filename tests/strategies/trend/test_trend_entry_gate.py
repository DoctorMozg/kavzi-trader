import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.domain.trend_gate_decision import TrendGateDecisionSchema
from kavzi_trader.news.news_item_schema import NewsItemSchema
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.strategies.trend.trend_entry_gate import TrendEntryGate
from kavzi_trader.strategies.trend.trend_gate_config import TrendGateConfigSchema
from kavzi_trader.strategies.trend.trend_gate_log import TrendGateLog

AS_OF = datetime(2026, 7, 16, 0, 1, tzinfo=UTC)
KEEP = {
    "verdict": "KEEP",
    "catalyst": "none",
    "reasoning": "No concrete negative catalyst.",
}
VETO = {
    "verdict": "VETO",
    "catalyst": "Exchange hack",
    "reasoning": "A venue listing SOL was drained.",
}


class ScriptedModel:
    """Replies with the scripted verdicts in order and keeps every prompt."""

    def __init__(self, *replies: dict[str, str]) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []

    def agent(self) -> Agent[None, TrendGateDecisionSchema]:
        def respond(messages: list[ModelMessage], _: AgentInfo) -> ModelResponse:
            self.prompts.append(str(messages[-1].parts[-1].content))  # type: ignore[union-attr]
            return ModelResponse(parts=[TextPart(json.dumps(self._replies.pop(0)))])

        return Agent(
            FunctionModel(respond), output_type=NativeOutput(TrendGateDecisionSchema)
        )


def _item(
    url: str, title: str, hours_ago: float, coins: tuple[str, ...]
) -> NewsItemSchema:
    return NewsItemSchema(
        url=url,
        title=title,
        source="cointelegraph",
        published_at=AS_OF - timedelta(hours=hours_ago),
        precision="exact",
        first_seen_at=AS_OF,
        coins=coins,
    )


@pytest.fixture
def config(tmp_path: Path) -> TrendGateConfigSchema:
    NewsStore(tmp_path / "news").add(
        [
            _item("a", "Solana DEX drained in exploit", 5, ("SOL",)),
            _item("b", "Bitcoin ETF inflows rise", 6, ("BTC",)),
            _item("late", "Solana recovers funds", 1, ("SOL",)),
        ]
    )
    return TrendGateConfigSchema(enabled=True, news_root=tmp_path / "news")


def _gate(model: ScriptedModel, config: TrendGateConfigSchema) -> TrendEntryGate:
    return TrendEntryGate(model.agent(), PromptLoader(), config, "system prompt v1")


class TestTrendEntryGate:
    async def test_majority_of_samples_decides(
        self, config: TrendGateConfigSchema
    ) -> None:
        model = ScriptedModel(VETO, KEEP, VETO)

        review = await _gate(model, config).review("SOLUSDT", AS_OF)

        assert review.decision == "VETO"
        assert [s.verdict for s in review.samples] == ["VETO", "KEEP", "VETO"]

    async def test_one_veto_of_three_keeps(self, config: TrendGateConfigSchema) -> None:
        review = await _gate(ScriptedModel(VETO, KEEP, KEEP), config).review(
            "SOLUSDT", AS_OF
        )

        assert review.decision == "KEEP"

    async def test_prompt_splits_coin_news_and_hides_headlines_inside_the_lag(
        self, config: TrendGateConfigSchema
    ) -> None:
        model = ScriptedModel(KEEP, KEEP, KEEP)

        review = await _gate(model, config).review("SOLUSDT", AS_OF)

        prompt = model.prompts[0]
        coin_part, other_part = prompt.split("Other crypto headlines")
        assert "Solana DEX drained" in coin_part
        assert "Bitcoin ETF inflows" in other_part
        assert "recovers funds" not in prompt
        assert (review.coin_headlines, review.other_headlines) == (1, 1)

    async def test_no_headlines_keeps_without_calling_the_model(
        self, tmp_path: Path
    ) -> None:
        model = ScriptedModel()
        config = TrendGateConfigSchema(news_root=tmp_path / "empty")

        review = await _gate(model, config).review("ADAUSDT", AS_OF)

        assert review.decision == "KEEP"
        assert review.samples == []
        assert model.prompts == []

    async def test_reviews_round_trip_through_the_log(
        self, config: TrendGateConfigSchema, tmp_path: Path
    ) -> None:
        review = await _gate(ScriptedModel(KEEP, KEEP, KEEP), config).review(
            "SOLUSDT", AS_OF
        )
        log = TrendGateLog(tmp_path / "gate.jsonl")

        log.append(review)

        assert log.read() == [review]
