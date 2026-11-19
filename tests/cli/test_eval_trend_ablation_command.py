from pathlib import Path

import pytest

from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from tests.cli.test_eval_trials_command import WINDOW, _invoke

SYMBOLS = ["--symbols", "BTCUSDT,ETHUSDT"]


class TestTrendAblationCommand:
    @pytest.mark.parametrize("arm", ["funding-crowding", "mid-exit", "fast-10"])
    def test_each_arm_reports_against_the_base_and_registers_once(
        self, config: AppConfig, archive: Path, arm: str
    ) -> None:
        out = config.system.results_dir / "ablation.md"
        args = ["trend-ablation", "--arm", arm, "--archive-dir", str(archive)]

        first = _invoke(config, *args, *SYMBOLS, *WINDOW, "--out", str(out))
        again = _invoke(config, *args, *SYMBOLS, *WINDOW, "--out", str(out))

        assert first.exception is None, first.output
        report = out.read_text(encoding="utf-8")
        assert f"Arm: {arm}:" in report
        assert "Sharpe difference (arm - base)" in report
        assert "Trial registered" in first.output
        assert "Trial registered" not in again.output
        assert trials_path(config).read_text(encoding="utf-8").count(arm) == 1


class TestBufferSweepCommand:
    def test_reports_every_band_and_fee_and_registers_base_fee_only(
        self, config: AppConfig, archive: Path
    ) -> None:
        out = config.system.results_dir / "sweep.md"

        result = _invoke(
            config,
            "buffer-sweep",
            "--bands", "0,0.2",
            "--cost-multipliers", "1,3",
            "--archive-dir", str(archive),
            *SYMBOLS, *WINDOW,
            "--out", str(out),
        )  # fmt: skip

        assert result.exception is None, result.output
        report = out.read_text(encoding="utf-8")
        assert "| Band | fee x1 | fee x3 |" in report
        assert report.count("\n| 0 |") == report.count("\n| 0.2 |") == 2
        trials = trials_path(config).read_text(encoding="utf-8").splitlines()
        assert len(trials) == 2
