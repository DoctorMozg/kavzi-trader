from pathlib import Path

import pytest

from kavzi_trader.config import AppConfig
from tests.replay.test_replay_runner import _regime_closes, _write_archive


@pytest.fixture
def config(app_config: AppConfig, tmp_path: Path) -> AppConfig:
    """App config writing results under the test's own directory."""
    system = app_config.system.model_copy(update={"results_dir": tmp_path / "out"})
    return app_config.model_copy(update={"system": system})


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    """A synthetic 1m archive of trending and falling regimes."""
    path = tmp_path / "archive"
    _write_archive(path, _regime_closes())
    return path
