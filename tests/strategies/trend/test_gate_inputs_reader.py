from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kavzi_trader.news.news_item_schema import NewsItemSchema
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.strategies.trend.gate_inputs_reader import GateInputsReader
from kavzi_trader.strategies.trend.trend_gate_config import TrendGateConfigSchema

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def _item(url: str, hours_ago: float, coins: tuple[str, ...]) -> NewsItemSchema:
    return NewsItemSchema(
        url=url,
        title=f"headline {url}",
        source="coindesk",
        published_at=NOW - timedelta(hours=hours_ago),
        precision="exact",
        first_seen_at=NOW,
        coins=coins,
    )


@pytest.fixture
def reader(tmp_path: Path) -> GateInputsReader:
    NewsStore(tmp_path).add(
        [
            _item("fresh", 1, ("SOL",)),  # inside the 2h lag: the gate can't see it yet
            _item("sol", 5, ("SOL",)),
            _item("both", 10, ("BTC", "ETH")),
            _item("market", 20, ()),
            _item("old", 100, ("BTC",)),  # outside the 72h window
        ]
    )
    config = TrendGateConfigSchema(enabled=True, news_root=tmp_path)
    return GateInputsReader(config, "claude-sonnet-5-5", "abc123")


class TestGateInputsReader:
    def test_counts_only_headlines_the_gate_could_see(
        self, reader: GateInputsReader
    ) -> None:
        inputs = reader.read(NOW)

        assert inputs.headlines == 3
        assert inputs.coin_headlines == {"SOL": 1, "BTC": 1, "ETH": 1}
        assert inputs.newest_at == NOW - timedelta(hours=5)

    def test_carries_the_gate_settings(self, reader: GateInputsReader) -> None:
        inputs = reader.read(NOW)

        assert (inputs.model_id, inputs.samples, inputs.prompt_sha) == (
            "claude-sonnet-5-5",
            3,
            "abc123",
        )
        assert (inputs.window_h, inputs.lag_h) == (72, 2.0)

    def test_empty_store_has_no_newest_headline(self, tmp_path: Path) -> None:
        config = TrendGateConfigSchema(enabled=True, news_root=tmp_path / "none")

        inputs = GateInputsReader(config, "m", "s").read(NOW)

        assert (inputs.headlines, inputs.newest_at, inputs.coin_headlines) == (
            0,
            None,
            {},
        )
