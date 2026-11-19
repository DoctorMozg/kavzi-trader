from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.config import AppConfig
from tests.cli.test_eval_run_command import _silenced_live_logs

WINDOW = [
    "--train-from",
    "2021-03-01",
    "--test-from",
    "2021-07-01",
    "--to",
    "2021-12-20",
]


@pytest.fixture
def symbols_file(tmp_path: Path) -> Path:
    path = tmp_path / "universe.txt"
    path.write_text(
        "# fixed before scoring\nBTCUSDT\n\nethusdt  # lower case is fine\n"
    )
    return path


def _invoke(config: AppConfig, *args: str) -> Result:
    with _silenced_live_logs():
        return CliRunner().invoke(
            eval_group, list(args), obj={"app_config": config}, standalone_mode=False
        )


def _walk(config: AppConfig, archive: Path, *extra: str) -> Result:
    return _invoke(
        config,
        "trend-walkforward",
        "--archive-dir", str(archive),
        "--lookbacks", "10,20,40",
        "--prereg", "test_prereg.md",
        *WINDOW,
        *extra,
    )  # fmt: skip


class TestTrendWalkForwardCommand:
    def test_writes_the_report_and_registers_one_trial(
        self, config: AppConfig, archive: Path, symbols_file: Path
    ) -> None:
        out = config.system.results_dir / "wf.md"

        result = _walk(
            config, archive, "--symbols-file", str(symbols_file), "--out", str(out)
        )

        assert result.exception is None, result.output
        assert "walk-forward net Sharpe" in result.output
        assert "1 trend trials" in result.output
        report = out.read_text()
        assert "2021-07-01 to 2021-12-19" in report
        assert "BTCUSDT, ETHUSDT" in report
        assert "| Test period | Chosen | L10 | L20 | L40 |" in report
        assert "Hindsight comparison" in report
        assert "evals/preregistrations/test_prereg.md" in report

    def test_symbols_and_symbols_file_together_are_rejected(
        self, config: AppConfig, archive: Path, symbols_file: Path
    ) -> None:
        result = _walk(
            config, archive, "--symbols", "BTCUSDT", "--symbols-file", str(symbols_file)
        )

        assert "not both" in str(result.exception)
