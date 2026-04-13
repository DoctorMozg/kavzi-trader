import logging
from decimal import ROUND_DOWN, Decimal

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.schemas import (
    PositionSizeResultSchema,
    VolatilityRegimeSchema,
)
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry

logger = logging.getLogger(__name__)

# Truncate toward zero at 8 decimals so rounded quantities never exceed the
# original value and breach margin/notional caps enforced just above.
_QUANTITY_QUANT = Decimal("0.00000001")


class PositionSizer:
    def __init__(
        self,
        config: RiskConfigSchema | None = None,
        tier_registry: SymbolTierRegistry | None = None,
    ) -> None:
        self._config = config or RiskConfigSchema()
        self._tier_registry = tier_registry

    def calculate_size(
        self,
        account_balance: Decimal,
        atr: Decimal,
        stop_loss_atr_multiplier: Decimal,
        regime: VolatilityRegimeSchema,
        entry_price: Decimal,
        leverage: int = 1,
        available_balance: Decimal | None = None,
        symbol: str | None = None,
    ) -> PositionSizeResultSchema:
        if atr <= 0 or entry_price <= 0:
            logger.warning(
                "Position sizer: atr=%s entry_price=%s, returning zero size",
                atr,
                entry_price,
            )
            return PositionSizeResultSchema(
                base_size=Decimal(0),
                adjusted_size=Decimal(0),
                size_multiplier=Decimal(0),
                risk_amount=Decimal(0),
            )

        # Tier-aware risk % and exposure cap
        risk_pct = self._config.risk_per_trade_percent
        max_exposure_pct = self._config.max_notional_percent
        if self._tier_registry is not None and symbol is not None:
            tier_config = self._tier_registry.get_config(symbol)
            risk_pct = tier_config.risk_per_trade_percent
            max_exposure_pct = tier_config.max_exposure_percent

        risk_amount = account_balance * (risk_pct / 100)
        stop_distance = atr * stop_loss_atr_multiplier

        base_size = risk_amount / stop_distance

        size_multiplier = regime.size_multiplier
        adjusted_size = base_size * size_multiplier

        # Notional floor: bump below-floor sizes up to the configured minimum
        # so the order clears Binance's per-symbol MIN_NOTIONAL filter.
        # Skipped when the regime multiplier has already zeroed the size
        # (LOW/EXTREME blocks must stay blocked).
        min_notional_floor = self._config.min_position_notional_usd
        if adjusted_size > 0 and min_notional_floor > 0 and entry_price > 0:
            min_size_by_notional = min_notional_floor / entry_price
            if adjusted_size < min_size_by_notional:
                logger.info(
                    "Notional floor: adjusted_size=%s bumped to min=%s "
                    "(min_notional=%s entry=%s)",
                    adjusted_size,
                    min_size_by_notional,
                    min_notional_floor,
                    entry_price,
                )
                adjusted_size = min_size_by_notional

        # Notional cap: apply early so downstream clamps see a bounded size
        if entry_price > 0 and max_exposure_pct > 0:
            max_notional = account_balance * (max_exposure_pct / 100)
            max_size_by_notional = max_notional / entry_price
            if adjusted_size > max_size_by_notional:
                logger.info(
                    "Notional cap: adjusted_size=%s capped to max=%s "
                    "(balance=%s max_notional_pct=%s entry=%s)",
                    adjusted_size,
                    max_size_by_notional,
                    account_balance,
                    max_exposure_pct,
                    entry_price,
                )
                adjusted_size = max_size_by_notional

        adjusted_size = adjusted_size.quantize(_QUANTITY_QUANT, rounding=ROUND_DOWN)

        if leverage > 0 and entry_price > 0:
            balance_for_margin = (
                available_balance if available_balance is not None else account_balance
            )
            max_size_by_margin = balance_for_margin * Decimal(leverage) / entry_price
            if adjusted_size > max_size_by_margin:
                logger.warning(
                    "Margin clamp: adjusted_size=%s exceeds max=%s "
                    "(balance=%s leverage=%s entry=%s)",
                    adjusted_size,
                    max_size_by_margin,
                    balance_for_margin,
                    leverage,
                    entry_price,
                )
                adjusted_size = max_size_by_margin.quantize(
                    _QUANTITY_QUANT,
                    rounding=ROUND_DOWN,
                )

        logger.debug(
            "Position sizer: balance=%s atr=%s sl_mult=%s regime=%s"
            " base=%s adjusted=%s risk=%s",
            account_balance,
            atr,
            stop_loss_atr_multiplier,
            regime.regime.value,
            base_size,
            adjusted_size,
            risk_amount,
        )

        return PositionSizeResultSchema(
            base_size=base_size.quantize(_QUANTITY_QUANT, rounding=ROUND_DOWN),
            adjusted_size=adjusted_size,
            size_multiplier=size_multiplier,
            risk_amount=risk_amount.quantize(_QUANTITY_QUANT, rounding=ROUND_DOWN),
        )
