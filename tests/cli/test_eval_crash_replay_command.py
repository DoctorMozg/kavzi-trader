import shutil
from pathlib import Path

from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from tests.cli.test_eval_trials_command import WINDOW, _invoke


class TestCrashReplayCommand:
    def test_replays_every_variant_and_prices_the_halving_rule(
        self, config: AppConfig, archive: Path
    ) -> None:
        for symbol in ("BTCUSDT", "ETHUSDT"):
            shutil.copytree(
                archive / "klines" / symbol, archive / "markPriceKlines" / symbol
            )
        out = config.system.results_dir / "crash.md"

        result = _invoke(
            config,
            "crash-replay",
            "--day", "2021-10-10",
            "--archive-dir", str(archive),
            "--symbols", "BTCUSDT,ETHUSDT",
            *WINDOW,
            "--out", str(out),
        )  # fmt: skip

        assert result.exception is None, result.output
        report = out.read_text(encoding="utf-8")
        for variant in ("no stop", "as live: last-price stop", "mark-price stop"):
            assert f"| {variant} |" in report
        assert "## Decisions" in report
        assert "vol-spike halving" in trials_path(config).read_text(encoding="utf-8")
