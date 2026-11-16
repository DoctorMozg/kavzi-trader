from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from kavzi_trader.archive.archive_dataset_schema import ArchiveDatasetSchema
from kavzi_trader.archive.archive_sync_schema import ArchiveSyncSchema
from kavzi_trader.cli.commands import archive
from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.config import AppConfig
from tests.cli.test_eval_run_command import _silenced_live_logs


class RecordingDownloader:
    synced: list[str]

    def __init__(self, *_args: object) -> None:
        pass

    async def sync(
        self, dataset: ArchiveDatasetSchema, symbol: str, _from_month: str
    ) -> ArchiveSyncSchema:
        RecordingDownloader.synced.append(symbol)
        return ArchiveSyncSchema(
            symbol=symbol, dataset=dataset.name, fetched=0, skipped=0
        )


@pytest.fixture
def synced(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    RecordingDownloader.synced = []
    monkeypatch.setattr(archive, "ArchiveDownloader", RecordingDownloader)
    return RecordingDownloader.synced


def _archive(config: AppConfig, root: Path, *args: str) -> Result:
    with _silenced_live_logs():
        return CliRunner().invoke(
            eval_group,
            ["archive", "--dataset", "funding", "--root", str(root), *args],
            obj={"app_config": config},
            standalone_mode=False,
        )


def test_traded_symbols_are_mirrored_by_default(
    app_config: AppConfig, tmp_path: Path, synced: list[str]
) -> None:
    result = _archive(app_config, tmp_path)

    assert result.exception is None
    assert synced == app_config.trading.symbols


def test_explicit_symbols_replace_the_traded_ones(
    app_config: AppConfig, tmp_path: Path, synced: list[str]
) -> None:
    result = _archive(app_config, tmp_path, "--symbols", " srmusdt, BTCUSDT ")

    assert result.exception is None
    assert synced == ["SRMUSDT", "BTCUSDT"]
