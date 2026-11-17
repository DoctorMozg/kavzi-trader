import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.config import AppConfig
from tests.cli.test_eval_run_command import _silenced_live_logs
from tests.replay.test_replay_runner import _regime_closes, _write_archive

WINDOW = ["--from", "2021-04-01", "--to", "2021-12-20"]


@pytest.fixture
def config(app_config: AppConfig, tmp_path: Path) -> AppConfig:
    system = app_config.system.model_copy(update={"results_dir": tmp_path / "out"})
    return app_config.model_copy(update={"system": system})


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    path = tmp_path / "archive"
    _write_archive(path, _regime_closes())
    return path


def _invoke(config: AppConfig, *args: str) -> Result:
    with _silenced_live_logs():
        return CliRunner().invoke(
            eval_group, list(args), obj={"app_config": config}, standalone_mode=False
        )


def _trend(config: AppConfig, archive: Path, lookbacks: str) -> Result:
    return _invoke(
        config,
        "trend",
        "--archive-dir", str(archive),
        "--symbols", "BTCUSDT,ETHUSDT",
        "--lookbacks", lookbacks,
        *WINDOW,
    )  # fmt: skip


def test_trend_runs_register_each_variant_once(
    config: AppConfig, archive: Path
) -> None:
    first = _trend(config, archive, "20")
    again = _trend(config, archive, "20")
    other = _trend(config, archive, "40")

    assert first.exception is None
    assert "1 trend trials so far" in first.output
    assert "registered" not in again.output
    assert "2 trend trials so far" in other.output


def test_trials_reports_deflated_sharpe_and_pbo(
    config: AppConfig, archive: Path
) -> None:
    for lookbacks in ("20", "40", "80"):
        _trend(config, archive, lookbacks)

    result = _invoke(config, "trials", "--blocks", "8")

    assert result.exception is None
    assert result.output.startswith("3 trend trials; best: long-flat lookbacks=")
    assert "deflated Sharpe" in result.output
    assert "over 3 trials and 70 CSCV splits" in result.output


def test_trials_without_any_registered_is_an_error(config: AppConfig) -> None:
    result = _invoke(config, "trials")

    assert result.exception is not None
    assert "no 'trend' trials" in str(result.exception)


@pytest.mark.parametrize("variant", ["vol-hold", "sma200"])
def test_benchmark_variants_register_as_their_own_trials(
    config: AppConfig, archive: Path, variant: str
) -> None:
    result = _invoke(
        config,
        "trend",
        "--archive-dir", str(archive),
        "--symbols", "BTCUSDT,ETHUSDT",
        "--variant", variant,
        *WINDOW,
    )  # fmt: skip

    assert result.exception is None
    assert "1 trend trials so far" in result.output
    lines = (config.system.results_dir / "evals" / "trials.jsonl").read_text()
    [trial] = [json.loads(line) for line in lines.splitlines()]
    assert trial["variant"].startswith(f"{variant} symbols=BTCUSDT,ETHUSDT ")
