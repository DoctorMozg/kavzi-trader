from pathlib import Path

import pytest

from kavzi_trader.cli.commands.trade import _load_tier_registry


def test_tier_registry_loads_from_any_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    registry = _load_tier_registry()

    assert registry.get_tier("BTCUSDT") is not None
