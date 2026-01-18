from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.paper.config import PaperTradingConfigSchema


class TestnetBinanceClient(BinanceClient):
    """Binance client configured for testnet endpoints."""

    def __init__(self, config: PaperTradingConfigSchema) -> None:
        super().__init__(
            api_key=config.testnet_api_key,
            api_secret=config.testnet_api_secret,
            testnet=True,
        )
