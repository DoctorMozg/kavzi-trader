import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from tests.cli.test_eval_run_command import _silenced_live_logs

WINDOW = ["--from", "2021-04-01", "--to", "2021-12-20"]


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


@pytest.mark.parametrize(
    ("variant", "description", "label"),
    [
        (
            "long-flat",
            "Donchian ensemble long/flat, lookbacks [20]",
            "long-flat lookbacks=20",
        ),
        (
            "long-short",
            "Donchian ensemble long/short, lookbacks [20]",
            "long-short lookbacks=20",
        ),
        ("vol-hold", "Vol-managed hold", "vol-hold "),
        ("sma200", "Long above the 200-day SMA", "sma200 "),
    ],
)
def test_each_variant_names_its_rule_and_trial(
    config: AppConfig, archive: Path, variant: str, description: str, label: str
) -> None:
    out = config.system.results_dir / "trend.md"

    result = _invoke(
        config,
        "trend",
        "--variant", variant,
        "--archive-dir", str(archive),
        "--symbols", "BTCUSDT,ETHUSDT",
        "--lookbacks", "20",
        "--out", str(out),
        *WINDOW,
    )  # fmt: skip

    assert result.exception is None, result.output
    assert description in out.read_text(encoding="utf-8")
    trial = json.loads(trials_path(config).read_text(encoding="utf-8"))
    assert trial["variant"].startswith(label)


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


def test_trend_with_its_own_prereg_cites_it_and_decides_alone(
    config: AppConfig, archive: Path
) -> None:
    out = config.system.results_dir / "fresh.md"

    result = _invoke(
        config,
        "trend",
        "--archive-dir", str(archive),
        "--symbols", "BTCUSDT,ETHUSDT",
        "--lookbacks", "20",
        "--prereg", "fresh_prereg.md",
        "--out", str(out),
        *WINDOW,
    )  # fmt: skip

    assert result.exception is None, result.output
    report = out.read_text()
    assert "evals/preregistrations/fresh_prereg.md" in report
    assert "decides on it alone" in report
    assert "both universes" not in report
