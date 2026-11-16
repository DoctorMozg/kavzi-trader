from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.paper.mode import TradingMode


class PaperTradingConfigSchema(BaseModel):
    """Configuration for paper trading."""

    mode: Annotated[TradingMode, Field()] = TradingMode.PAPER
    initial_balance_usdt: Annotated[Decimal, Field(ge=0)] = Decimal(10000)
    # False keeps Redis state and restores the paper book on start.
    reset_on_start: Annotated[bool, Field()] = True
    # Binance USDT-M VIP0 taker fee. The prior 0.001 overstated cost ~2x.
    commission_rate: Annotated[Decimal, Field(ge=0)] = Decimal("0.0005")

    model_config = ConfigDict(frozen=True)
