from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.paper.mode import TradingMode


class PaperTradingConfigSchema(BaseModel):
    """Configuration for paper trading."""

    mode: Annotated[TradingMode, Field()] = TradingMode.PAPER
    initial_balance_usdt: Annotated[Decimal, Field(ge=0)] = Decimal(10000)
    commission_rate: Annotated[Decimal, Field(ge=0)] = Decimal("0.001")

    model_config = ConfigDict(frozen=True)
