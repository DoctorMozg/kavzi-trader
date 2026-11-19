import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import click
import pytest
from click.testing import CliRunner
from pydantic import SecretStr

from kavzi_trader.cli import composition, spine_composition
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
        "kavzi_trader.cli.commands.trade.build_state_manager",
        lambda *_: mock_manager,
    )
    monkeypatch.setattr(trade_module, "build_exchange", lambda _: AsyncMock())
    ctx = click.Context(trade, obj={"app_config": AppConfig.from_env()})
    callback = trade_module.status.callback
    assert callback is not None
    with ctx:
        callback()
    captured = capsys.readouterr()
    assert "Positions: 0" in captured.out
    assert "Open orders: 0" in captured.out


class _LoopRecorder:
    """Records which event loop each awaited call runs on, and whether it closed."""

    def __init__(self) -> None:
        self.loops: list[asyncio.AbstractEventLoop] = []
        self.closed = False

    def note(self) -> None:
        self.loops.append(asyncio.get_running_loop())

    async def connect(self) -> None:
        self.note()

    async def close(self) -> None:
        self.note()
        self.closed = True

    async def get_all_positions(self) -> list[object]:
        self.note()
        return []

    async def get_open_orders(self) -> list[object]:
        self.note()
        return []

    async def read(self, *_args: object, **_kwargs: object) -> list[object]:
        self.note()
        return []


@pytest.mark.parametrize("command", ["status", "positions"])
def test_state_commands_use_one_event_loop_and_close(monkeypatch, command) -> None:
    recorder = _LoopRecorder()
    exchange = _LoopRecorder()
    monkeypatch.setattr(trade_module, "build_state_manager", lambda *_: recorder)
    monkeypatch.setattr(trade_module, "build_exchange", lambda _: exchange)

    result = CliRunner().invoke(
        trade, [command], obj={"app_config": AppConfig.from_env()}
    )

    assert result.exit_code == 0, result.output
    assert len(recorder.loops) >= 3
    assert len(set(recorder.loops + exchange.loops)) == 1, "calls ran on many loops"
    assert recorder.closed
    # The exchange client owns an aiohttp session; leaving it open warns at exit.
    assert exchange.closed


def test_history_uses_one_event_loop_and_closes(monkeypatch) -> None:
    recorder = _LoopRecorder()
    monkeypatch.setattr(trade_module, "RedisStateClient", lambda *_: recorder)
    monkeypatch.setattr(trade_module, "RedisEventStore", lambda *_: recorder)

    result = CliRunner().invoke(
        trade, ["history"], obj={"app_config": AppConfig.from_env()}
    )

    assert result.exit_code == 0, result.output
    assert len(recorder.loops) >= 3
    assert len(set(recorder.loops)) == 1, "calls ran on different event loops"
    assert recorder.closed


@pytest.mark.asyncio
async def test_start_orchestrator_uses_configured_runtime_values(
    monkeypatch, llm_app_config: AppConfig
) -> None:
    captured: dict[str, Any] = {}

    app_config = llm_app_config
    app_config = app_config.model_copy(
        update={
            "api": app_config.api.model_copy(
                update={
                    "binance": app_config.api.binance.model_copy(
                        update={
                            "api_key": SecretStr("test-key"),
                            "api_secret": SecretStr("test-secret"),
                        },
                    ),
                },
            ),
            "brain": app_config.brain.model_copy(
                update={
                    "openrouter_api_key": SecretStr("test-openrouter-key"),
                    "anthropic_api_key": SecretStr("test-anthropic-key"),
                },
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
            "ui": app_config.ui.model_copy(update={"enabled": False}),
        },
    )

    redis_client = AsyncMock()
    redis_client.connect = AsyncMock()

    def _build_fake_state_manager(*_args: object, **_kw: object) -> AsyncMock:
        manager = AsyncMock()
        manager.set_protective_order_placer = Mock()
        return manager

    monkeypatch.setattr(
        composition,
        "build_state_manager",
        _build_fake_state_manager,
    )
    mock_exchange = AsyncMock()
    monkeypatch.setattr(composition, "build_exchange", lambda _: mock_exchange)
    monkeypatch.setattr(composition, "RedisStateClient", lambda *_: redis_client)
    monkeypatch.setattr(composition, "RedisEventStore", lambda *_: object())
    monkeypatch.setattr(
        composition,
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

    monkeypatch.setattr(composition, "MarketDataCache", FakeCache)
    ws_client = Mock()
    stream_manager = Mock()
    monkeypatch.setattr(composition, "BinanceWebsocketClient", lambda **_: ws_client)
    monkeypatch.setattr(composition, "LiveStreamManager", lambda **_: stream_manager)

    monkeypatch.setattr(
        composition,
        "LiveOrderFlowFetcher",
        lambda **_: object(),
    )
    monkeypatch.setattr(composition, "LiveDependenciesProvider", lambda **_: object())
    monkeypatch.setattr(spine_composition, "LiveAtrProvider", lambda *_: object())
    monkeypatch.setattr(spine_composition, "LivePriceProvider", lambda *_: object())
    monkeypatch.setattr(
        spine_composition,
        "ExecutionEngine",
        lambda **_: SimpleNamespace(protective_orders=object()),
    )
    monkeypatch.setattr(composition, "PromptLoader", Mock)
    monkeypatch.setattr(composition, "ContextBuilder", lambda: object())

    class FakeFactory:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def create_analyst_agent(self) -> object:
            return object()

        def create_trader_agent(self) -> object:
            return object()

        def create_synthesizer_agent(self, _config: object) -> object:
            return object()

    monkeypatch.setattr(composition, "AgentFactory", FakeFactory)
    monkeypatch.setattr(composition, "ScoutFilter", lambda *_: object())
    monkeypatch.setattr(composition, "AnalystAgent", lambda *_: object())
    monkeypatch.setattr(composition, "TraderAgent", lambda *_: object())
    monkeypatch.setattr(composition, "AgentRouter", lambda *_a, **_kw: object())
    monkeypatch.setattr(spine_composition, "PositionManager", lambda **_: object())
    monkeypatch.setattr(composition, "DataIngestLoop", lambda *_: object())

    def build_order_flow_loop(_fetcher, interval_s: int) -> object:
        captured["order_flow_interval_s"] = interval_s
        return object()

    def build_reasoning_plugin(**kwargs) -> object:
        captured["reasoning_interval_s"] = kwargs["interval_s"]
        return object()

    def build_position_loop(**kwargs) -> object:
        captured["position_interval_s"] = kwargs["interval_s"]
        return object()

    monkeypatch.setattr(composition, "OrderFlowLoop", build_order_flow_loop)
    monkeypatch.setattr(composition, "LlmPipelinePlugin", build_reasoning_plugin)
    monkeypatch.setattr(composition, "StrategyLoop", lambda **_: object())
    monkeypatch.setattr(composition, "ExecutionLoop", lambda **_: object())
    monkeypatch.setattr(
        spine_composition,
        "PositionManagementLoop",
        build_position_loop,
    )

    class FakeTradingOrchestrator:
        async def start(self) -> None:
            return None

    def build_orchestrator(**kwargs) -> FakeTradingOrchestrator:
        captured["shutdown_hooks"] = kwargs["shutdown_hooks"]
        return FakeTradingOrchestrator()

    monkeypatch.setattr(composition, "TradingOrchestrator", build_orchestrator)

    await trade_module._start_orchestrator(app_config)

    assert captured["max_candles"] == 321
    assert captured["cache_interval"] == "1m"
    assert captured["order_flow_interval_s"] == 22
    assert captured["reasoning_interval_s"] == 33
    assert captured["position_interval_s"] == 44
    ws_client.set_on_error.assert_called_once_with(stream_manager.handle_ws_error)
    # Close order: feed first, then the exchange session, then Redis.
    assert list(captured["shutdown_hooks"]) == ["websocket", "exchange", "redis"]
