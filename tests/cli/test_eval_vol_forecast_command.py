from pathlib import Path

import pandas as pd
import pytest

from kavzi_trader.config import AppConfig
from kavzi_trader.evals import chronos_vol_forecaster
from kavzi_trader.evals.dvol_history import DvolHistory
from kavzi_trader.evals.realized_variance import RealizedVariance
from tests.cli.test_eval_trials_command import _invoke


class _TrailingRv:
    """Stands in for Chronos-2: forecasts trailing 7-day variance, no download."""

    def __init__(self, first: pd.Timestamp, revision: str) -> None:
        self._first = first

    @property
    def name(self) -> str:
        return "chronos-2"

    def forecast(self, returns: pd.DataFrame) -> pd.DataFrame:
        backward = RealizedVariance.backward(returns, 7)
        scored = pd.Series(backward.index >= self._first, index=backward.index)
        return backward.where(scored, axis=0)


@pytest.fixture
def dvol_dir(tmp_path: Path) -> Path:
    days = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    for currency in ("BTC", "ETH"):
        DvolHistory.save(pd.Series(60.0, index=days, name=currency), tmp_path / "dvol")
    return tmp_path / "dvol"


class TestVolForecastCommand:
    def test_scores_every_forecaster_and_reports_stage_b(
        self,
        config: AppConfig,
        archive: Path,
        dvol_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(chronos_vol_forecaster, "ChronosVolForecaster", _TrailingRv)
        out = config.system.results_dir / "vol.md"

        result = _invoke(
            config,
            "vol-forecast",
            "--chronos-revision", "test",
            "--dvol-dir", str(dvol_dir),
            "--archive-dir", str(archive),
            "--symbols", "BTCUSDT,ETHUSDT",
            "--from", "2021-09-01",
            "--to", "2021-12-20",
            "--out", str(out),
        )  # fmt: skip

        assert result.exception is None, result.output
        report = out.read_text(encoding="utf-8")
        for name in ("har", "har-dvol", "lgbm", "chronos-2"):
            assert f"| {name} | rolling-30d |" in report
        assert "| har-dvol | har |" in report
        assert "## Trading test (stage B)" in report
