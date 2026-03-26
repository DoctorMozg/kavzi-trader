from kavzi_trader.paper.mode import TradingMode


def test_trading_mode_values() -> None:
    assert TradingMode.LIVE.value == "LIVE"
    assert TradingMode.TESTNET.value == "TESTNET"
    assert TradingMode.PAPER.value == "PAPER"
    assert TradingMode.DISABLED.value == "DISABLED"
