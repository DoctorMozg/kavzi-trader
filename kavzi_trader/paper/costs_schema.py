from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class PaperCostsSchema(BaseModel):
    """Fees, slippage and margin rates the paper exchange charges."""

    # Binance USDT-M VIP0 rates.
    taker_fee_rate: Annotated[Decimal, Field(ge=0)] = Decimal("0.0005")
    maker_fee_rate: Annotated[Decimal, Field(ge=0)] = Decimal("0.0002")
    # Adverse price move applied to every taker fill.
    slippage_bps: Annotated[Decimal, Field(ge=0)] = Decimal(0)
    # Binance's lowest BTCUSDT bracket; one rate for every symbol.
    maintenance_margin_rate: Annotated[Decimal, Field(ge=0, lt=1)] = Decimal("0.004")

    model_config = ConfigDict(frozen=True)
