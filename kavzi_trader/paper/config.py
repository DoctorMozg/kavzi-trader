from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.paper.mode import TradingMode


class PaperTradingConfigSchema(BaseModel):
    """Configuration for paper trading."""

    mode: Annotated[TradingMode, Field()] = TradingMode.TESTNET
    initial_balance_usdt: Annotated[Decimal, Field(ge=0)] = Decimal("10000")
    commission_rate: Annotated[Decimal, Field(ge=0)] = Decimal("0.001")
    testnet_api_key: Annotated[str | None, Field()] = None
    testnet_api_secret: Annotated[str | None, Field()] = None
    testnet_base_url: Annotated[str, Field()] = "https://testnet.binance.vision"
    testnet_ws_url: Annotated[str, Field()] = "wss://testnet.binance.vision/ws"

    model_config = ConfigDict(frozen=True)
