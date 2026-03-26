from unittest.mock import AsyncMock

import click
import pytest
from click.testing import CliRunner

from kavzi_trader.cli.commands import trade as trade_module
from kavzi_trader.cli.commands.trade import trade
from kavzi_trader.config import AppConfig


def test_trade_start_dry_run(monkeypatch) -> None:
    runner = CliRunner()
    result = runner.invoke(
        trade,
        ["start", "--dry-run"],
        obj={"app_config": AppConfig.from_env()},
    )

    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_trade_status_outputs_counts(monkeypatch, capsys) -> None:
    mock_manager = AsyncMock()
    mock_manager.connect = AsyncMock()
    mock_manager.get_all_positions = AsyncMock(return_value=[])
    mock_manager.get_open_orders = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "kavzi_trader.cli.commands.trade._build_state_manager",
        lambda _: mock_manager,
    )
    ctx = click.Context(trade, obj={"app_config": AppConfig.from_env()})
    with ctx:
        trade_module.status.callback()
    captured = capsys.readouterr()
    assert "Positions: 0" in captured.out
    assert "Open orders: 0" in captured.out


@pytest.mark.asyncio
async def test_start_orchestrator_uses_configured_runtime_values(
    monkeypatch,
) -> None:
    captured: dict[str, int | str | None] = {}

    app_config = AppConfig.from_env()
    app_config = app_config.model_copy(
        update={
            "api": app_config.api.model_copy(
                update={
                    "binance": app_config.api.binance.model_copy(
                        update={
                            "api_key": "test-key",
                            "api_secret": "test-secret",
                        },
                    ),
                },
            ),
            "brain": app_config.brain.model_copy(
                update={"openrouter_api_key": "test-openrouter-key"},
            ),
            "trading": app_config.trading.model_copy(
                update={"interval": "1m", "history_candles": 321},
            ),
            "orchestrator": app_config.orchestrator.model_copy(
                update={
                    "order_flow_fetch_interval_s": 22,
                    "reasoning_interval_s": 33,
                    "position_check_interval_s": 44,
                },
            ),
            "reporting": app_config.reporting.model_copy(update={"enabled": False}),
        },
    )

    redis_client = AsyncMock()
    redis_client.connect = AsyncMock()

    monkeypatch.setattr(trade_module, "rebuild_deferred_models", lambda: None)
    monkeypatch.setattr(
        trade_module,
        "_build_state_manager",
        lambda *_args, **_kw: AsyncMock(),
    )
    monkeypatch.setattr(trade_module, "_build_exchange", lambda _: object())
    monkeypatch.setattr(trade_module, "RedisStateClient", lambda *_: redis_client)
    monkeypatch.setattr(trade_module, "RedisEventStore", lambda *_: object())
    monkeypatch.setattr(
        trade_module,
        "TechnicalIndicatorCalculator",
        lambda: object(),
    )

    class FakeCache:
        def __init__(
            self,
            *,
            symbols,
            indicator_calculator,
            max_candles=None,
        ) -> None:
            _ = symbols
            _ = indicator_calculator
            captured["max_candles"] = max_candles

        async def initialize(self, exchange, interval: str) -> None:
            _ = exchange
            captured["cache_interval"] = interval

    monkeypatch.setattr(trade_module, "MarketDataCache", FakeCache)
    monkeypatch.setattr(trade_module, "BinanceWebsocketClient", lambda **_: object())
    monkeypatch.setattr(trade_module, "LiveStreamManager", lambda **_: object())

    monkeypatch.setattr(
        trade_module,
        "LiveOrderFlowFetcher",
        lambda **_: object(),
    )
    monkeypatch.setattr(trade_module, "LiveDependenciesProvider", lambda **_: object())
    monkeypatch.setattr(trade_module, "LiveAtrProvider", lambda *_: object())
    monkeypatch.setattr(trade_module, "ExecutionEngine", lambda **_: object())
    monkeypatch.setattr(trade_module, "PromptLoader", lambda: object())
    monkeypatch.setattr(trade_module, "ContextBuilder", lambda: object())

    class FakeFactory:
        def __init__(self, *_args) -> None:
            pass

        def create_scout_agent(self) -> object:
            return object()

        def create_analyst_agent(self) -> object:
            return object()

        def create_trader_agent(self) -> object:
            return object()

    monkeypatch.setattr(trade_module, "AgentFactory", FakeFactory)
    monkeypatch.setattr(trade_module, "ScoutAgent", lambda *_: object())
    monkeypatch.setattr(trade_module, "AnalystAgent", lambda *_: object())
    monkeypatch.setattr(trade_module, "TraderAgent", lambda *_: object())
    monkeypatch.setattr(trade_module, "AgentRouter", lambda *_: object())
    monkeypatch.setattr(trade_module, "PositionManager", lambda **_: object())
    monkeypatch.setattr(trade_module, "DataIngestLoop", lambda *_: object())

    def build_order_flow_loop(_fetcher, interval_s: int) -> object:
        captured["order_flow_interval_s"] = interval_s
        return object()

    def build_reasoning_loop(**kwargs) -> object:
        captured["reasoning_interval_s"] = kwargs["interval_s"]
        return object()

    def build_position_loop(**kwargs) -> object:
        captured["position_interval_s"] = kwargs["interval_s"]
        return object()

    monkeypatch.setattr(trade_module, "OrderFlowLoop", build_order_flow_loop)
    monkeypatch.setattr(trade_module, "ReasoningLoop", build_reasoning_loop)
    monkeypatch.setattr(trade_module, "ExecutionLoop", lambda **_: object())
    monkeypatch.setattr(
        trade_module,
        "PositionManagementLoop",
        build_position_loop,
    )
    monkeypatch.setattr(trade_module, "HealthChecker", lambda: object())

    class FakeTradingOrchestrator:
        async def start(self) -> None:
            return None

    monkeypatch.setattr(
        trade_module,
        "TradingOrchestrator",
        lambda **_: FakeTradingOrchestrator(),
    )

    await trade_module._start_orchestrator(app_config)

    assert captured["max_candles"] == 321
    assert captured["cache_interval"] == "1m"
    assert captured["order_flow_interval_s"] == 22
    assert captured["reasoning_interval_s"] == 33
    assert captured["position_interval_s"] == 44
