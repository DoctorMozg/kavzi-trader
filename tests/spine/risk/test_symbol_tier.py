from decimal import Decimal
from pathlib import Path

import pytest

from kavzi_trader.spine.risk.symbol_tier import (
    SymbolTier,
    SymbolTierConfigSchema,
)
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry


@pytest.fixture()
def tier_configs() -> dict[SymbolTier, SymbolTierConfigSchema]:
    return {
        SymbolTier.TIER_1: SymbolTierConfigSchema.model_validate(
            {
                "risk_per_trade_percent": "2.0",
                "max_leverage": 5,
                "max_exposure_percent": "15.0",
                "min_confidence": "0.70",
                "crowded_long_zscore": "2.0",
                "crowded_short_zscore": "-2.0",
            },
        ),
        SymbolTier.TIER_2: SymbolTierConfigSchema.model_validate(
            {
                "risk_per_trade_percent": "1.5",
                "max_leverage": 3,
                "max_exposure_percent": "8.0",
                "min_confidence": "0.75",
                "crowded_long_zscore": "2.5",
                "crowded_short_zscore": "-2.5",
            },
        ),
        SymbolTier.TIER_3: SymbolTierConfigSchema.model_validate(
            {
                "risk_per_trade_percent": "1.0",
                "max_leverage": 2,
                "max_exposure_percent": "3.0",
                "min_confidence": "0.85",
                "crowded_long_zscore": "3.5",
                "crowded_short_zscore": "-3.5",
            },
        ),
    }


@pytest.fixture()
def symbol_map() -> dict[str, SymbolTier]:
    return {
        "BTCUSDT": SymbolTier.TIER_1,
        "ETHUSDT": SymbolTier.TIER_1,
        "SOLUSDT": SymbolTier.TIER_2,
        "DOGEUSDT": SymbolTier.TIER_3,
    }


@pytest.fixture()
def registry(
    tier_configs: dict[SymbolTier, SymbolTierConfigSchema],
    symbol_map: dict[str, SymbolTier],
) -> SymbolTierRegistry:
    return SymbolTierRegistry(
        tier_configs=tier_configs,
        symbol_map=symbol_map,
    )


def test_known_symbol_returns_correct_tier(
    registry: SymbolTierRegistry,
) -> None:
    assert registry.get_tier("BTCUSDT") == SymbolTier.TIER_1
    assert registry.get_tier("ETHUSDT") == SymbolTier.TIER_1
    assert registry.get_tier("SOLUSDT") == SymbolTier.TIER_2
    assert registry.get_tier("DOGEUSDT") == SymbolTier.TIER_3


def test_unknown_symbol_defaults_to_tier3(
    registry: SymbolTierRegistry,
) -> None:
    assert registry.get_tier("UNKNOWNUSDT") == SymbolTier.TIER_3


def test_get_config_returns_tier_config(
    registry: SymbolTierRegistry,
) -> None:
    config = registry.get_config("BTCUSDT")
    assert config.risk_per_trade_percent == Decimal("2.0")
    assert config.max_leverage == 5
    assert config.min_confidence == Decimal("0.70")


def test_get_config_unknown_symbol_returns_tier3_config(
    registry: SymbolTierRegistry,
) -> None:
    config = registry.get_config("RANDOMUSDT")
    assert config.risk_per_trade_percent == Decimal("1.0")
    assert config.max_leverage == 2
    assert config.min_confidence == Decimal("0.85")


def test_from_yaml(tmp_path: Path) -> None:
    yaml_content = """\
tiers:
  TIER_1:
    risk_per_trade_percent: "2.0"
    max_leverage: 5
    max_exposure_percent: "15.0"
    min_confidence: "0.70"
    crowded_long_zscore: "2.0"
    crowded_short_zscore: "-2.0"
    symbols:
      - BTCUSDT
      - ETHUSDT

  TIER_2:
    risk_per_trade_percent: "1.5"
    max_leverage: 3
    max_exposure_percent: "8.0"
    min_confidence: "0.75"
    crowded_long_zscore: "2.5"
    crowded_short_zscore: "-2.5"
    symbols:
      - SOLUSDT

  TIER_3:
    risk_per_trade_percent: "1.0"
    max_leverage: 2
    max_exposure_percent: "3.0"
    min_confidence: "0.85"
    crowded_long_zscore: "3.5"
    crowded_short_zscore: "-3.5"
    symbols:
      - DOGEUSDT
"""
    yaml_file = tmp_path / "tiers.yaml"
    yaml_file.write_text(yaml_content)

    registry = SymbolTierRegistry.from_yaml(yaml_file)

    assert registry.get_tier("BTCUSDT") == SymbolTier.TIER_1
    assert registry.get_tier("SOLUSDT") == SymbolTier.TIER_2
    assert registry.get_tier("DOGEUSDT") == SymbolTier.TIER_3
    assert registry.get_tier("NEWCOINUSDT") == SymbolTier.TIER_3

    config = registry.get_config("ETHUSDT")
    assert config.max_leverage == 5


def test_from_yaml_missing_tier3_raises(tmp_path: Path) -> None:
    yaml_content = """\
tiers:
  TIER_1:
    risk_per_trade_percent: "2.0"
    max_leverage: 5
    max_exposure_percent: "15.0"
    min_confidence: "0.70"
    crowded_long_zscore: "2.0"
    crowded_short_zscore: "-2.0"
    symbols:
      - BTCUSDT
"""
    yaml_file = tmp_path / "tiers.yaml"
    yaml_file.write_text(yaml_content)

    with pytest.raises(ValueError, match="TIER_3"):
        SymbolTierRegistry.from_yaml(yaml_file)


def test_tier_config_is_frozen() -> None:
    config = SymbolTierConfigSchema.model_validate(
        {
            "risk_per_trade_percent": "1.0",
            "max_leverage": 2,
            "max_exposure_percent": "3.0",
            "min_confidence": "0.85",
            "crowded_long_zscore": "3.5",
            "crowded_short_zscore": "-3.5",
        },
    )
    with pytest.raises(Exception):
        config.max_leverage = 10  # type: ignore[misc]
