import logging
from pathlib import Path
from typing import Any

import yaml

from kavzi_trader.spine.risk.symbol_tier import SymbolTier, SymbolTierConfigSchema

logger = logging.getLogger(__name__)


class SymbolTierRegistry:
    """Maps trading symbols to their tier and associated risk config."""

    def __init__(
        self,
        tier_configs: dict[SymbolTier, SymbolTierConfigSchema],
        symbol_map: dict[str, SymbolTier],
    ) -> None:
        self._tier_configs = tier_configs
        self._symbol_map = symbol_map

    def get_tier(self, symbol: str) -> SymbolTier:
        """Return the tier for a symbol. Unknown symbols default to TIER_3."""
        return self._symbol_map.get(symbol, SymbolTier.TIER_3)

    def get_config(self, symbol: str) -> SymbolTierConfigSchema:
        """Return the tier config for a symbol."""
        tier = self.get_tier(symbol)
        return self._tier_configs[tier]

    @classmethod
    def from_yaml(cls, path: Path) -> "SymbolTierRegistry":
        """Load tier configuration from a YAML file."""
        raw = yaml.safe_load(path.read_text())
        tiers_raw: dict[str, Any] = raw["tiers"]

        tier_configs: dict[SymbolTier, SymbolTierConfigSchema] = {}
        symbol_map: dict[str, SymbolTier] = {}

        for tier_name, tier_data in tiers_raw.items():
            tier = SymbolTier(tier_name)
            symbols: list[str] = tier_data.pop("symbols", [])
            config = SymbolTierConfigSchema.model_validate(tier_data)
            tier_configs[tier] = config
            for sym in symbols:
                symbol_map[sym] = tier

        if SymbolTier.TIER_3 not in tier_configs:
            msg = "tiers.yaml must define TIER_3 (used as default for unknown symbols)"
            raise ValueError(msg)

        logger.info(
            "Loaded %d tier configs covering %d symbols",
            len(tier_configs),
            len(symbol_map),
        )
        return cls(tier_configs=tier_configs, symbol_map=symbol_map)
