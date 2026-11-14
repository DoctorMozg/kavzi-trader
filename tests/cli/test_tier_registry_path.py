from pathlib import Path

import pytest

from kavzi_trader.cli.composition import load_tier_registry
from kavzi_trader.domain.symbol_tier import SymbolTier


def test_tier_registry_loads_from_any_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    registry = load_tier_registry()

    assert registry.get_tier("BTCUSDT") is SymbolTier.TIER_1
