from click.testing import CliRunner

from kavzi_trader.cli.commands.model import model
from kavzi_trader.config import AppConfig


def test_model_status_no_api_key() -> None:
    runner = CliRunner()
    app_config = AppConfig.from_env()
    result = runner.invoke(model, ["status"], obj={"app_config": app_config})

    assert result.exit_code == 0
    assert "NOT CONFIGURED" in result.output
