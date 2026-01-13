from decimal import Decimal

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.schemas import (
    PositionSizeResultSchema,
    VolatilityRegimeSchema,
)


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
    ) -> PositionSizeResultSchema:
        if atr <= 0 or entry_price <= 0:
            return PositionSizeResultSchema(
                base_size=Decimal("0"),
                adjusted_size=Decimal("0"),
                size_multiplier=Decimal("0"),
                risk_amount=Decimal("0"),
            )

        risk_amount = account_balance * (self._config.risk_per_trade_percent / 100)
        stop_distance = atr * stop_loss_atr_multiplier

        base_size = risk_amount / stop_distance

        size_multiplier = regime.size_multiplier
        adjusted_size = base_size * size_multiplier

        adjusted_size = Decimal(str(round(float(adjusted_size), 8)))

        return PositionSizeResultSchema(
            base_size=Decimal(str(round(float(base_size), 8))),
            adjusted_size=adjusted_size,
            size_multiplier=size_multiplier,
            risk_amount=Decimal(str(round(float(risk_amount), 8))),
        )
