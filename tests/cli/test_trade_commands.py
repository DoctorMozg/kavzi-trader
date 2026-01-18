from unittest.mock import AsyncMock

import click
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
