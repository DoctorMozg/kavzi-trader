from kavzi_trader.paper.client import TestnetBinanceClient
from kavzi_trader.paper.config import PaperTradingConfigSchema


def test_testnet_client_uses_testnet() -> None:
    config = PaperTradingConfigSchema(
        testnet_api_key="key",
        testnet_api_secret="secret",
    )
    client = TestnetBinanceClient(config)

    assert client.testnet is True
