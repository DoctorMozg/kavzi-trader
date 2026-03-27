import logging
from decimal import Decimal

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.schemas import (
    PositionSizeResultSchema,
    VolatilityRegimeSchema,
)

logger = logging.getLogger(__name__)


class PositionSizer:
    def __init__(self, config: RiskConfigSchema | None = None) -> None:
        self._config = config or RiskConfigSchema()

    def calculate_size(
        self,
        account_balance: Decimal,
        atr: Decimal,
        stop_loss_atr_multiplier: Decimal,
        regime: VolatilityRegimeSchema,
        entry_price: Decimal,
        leverage: int = 1,
        available_balance: Decimal | None = None,
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

        risk_amount = account_balance * (self._config.risk_per_trade_percent / 100)
        stop_distance = atr * stop_loss_atr_multiplier

        base_size = risk_amount / stop_distance

        size_multiplier = regime.size_multiplier
        adjusted_size = base_size * size_multiplier

        # Notional cap: apply early so downstream clamps see a bounded size
        if entry_price > 0 and self._config.max_notional_percent > 0:
            max_notional = account_balance * (self._config.max_notional_percent / 100)
            max_size_by_notional = max_notional / entry_price
            if adjusted_size > max_size_by_notional:
                logger.info(
                    "Notional cap: adjusted_size=%s capped to max=%s "
                    "(balance=%s max_notional_pct=%s entry=%s)",
                    adjusted_size,
                    max_size_by_notional,
                    account_balance,
                    self._config.max_notional_percent,
                    entry_price,
                )
                adjusted_size = max_size_by_notional

        adjusted_size = Decimal(str(round(float(adjusted_size), 8)))

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
                adjusted_size = Decimal(
                    str(round(float(max_size_by_margin), 8)),
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
            base_size=Decimal(str(round(float(base_size), 8))),
            adjusted_size=adjusted_size,
            size_multiplier=size_multiplier,
            risk_amount=Decimal(str(round(float(risk_amount), 8))),
        )
