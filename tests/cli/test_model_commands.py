from click.testing import CliRunner

from kavzi_trader.cli.commands.model import model


def test_model_status_command() -> None:
    runner = CliRunner()
    result = runner.invoke(model, ["status"])

    assert result.exit_code == 0
    assert "not configured" in result.output
