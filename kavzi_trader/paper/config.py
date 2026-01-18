from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.paper.mode import TradingMode


class PaperTradingConfigSchema(BaseModel):
    """Configuration for paper trading via Binance testnet."""

    mode: Annotated[TradingMode, Field()] = TradingMode.TESTNET
    testnet_api_key: Annotated[str | None, Field()] = None
    testnet_api_secret: Annotated[str | None, Field()] = None
    testnet_base_url: Annotated[str, Field()] = "https://testnet.binance.vision"
    testnet_ws_url: Annotated[str, Field()] = "wss://testnet.binance.vision/ws"

    model_config = ConfigDict(frozen=True)
