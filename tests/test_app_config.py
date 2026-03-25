from kavzi_trader.config import AppConfig, TradingConfigSchema
from kavzi_trader.orchestrator.config import OrchestratorConfigSchema


def test_trading_config_defaults() -> None:
    config = TradingConfigSchema()

    assert config.interval == "1m"
    assert config.history_candles == 1000


def test_orchestrator_config_defaults() -> None:
    config = OrchestratorConfigSchema()

    assert config.reasoning_interval_s == 30


def test_app_config_from_env_timing_defaults() -> None:
    config = AppConfig.from_env()

    assert config.trading.interval == "1m"
    assert config.trading.history_candles == 1000
    assert config.orchestrator.reasoning_interval_s == 30
