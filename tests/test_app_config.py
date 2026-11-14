import pytest
import yaml
from pydantic import ValidationError

from kavzi_trader.config import CONFIG_DIR, AppConfig, TradingConfigSchema
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.orchestrator.config import OrchestratorConfigSchema


def test_trading_config_defaults() -> None:
    config = TradingConfigSchema()

    assert config.interval == "1m"
    assert config.history_candles == 1000


def test_orchestrator_config_defaults() -> None:
    config = OrchestratorConfigSchema()

    assert config.reasoning_interval_s == 60
    assert config.order_flow_fetch_interval_s == 300


def test_app_config_from_env_timing_defaults() -> None:
    config = AppConfig.from_env()

    assert config.trading.interval == "15m"
    assert config.trading.history_candles == 1000
    assert config.orchestrator.reasoning_interval_s == 120


def test_history_candles_is_capped_by_binance_kline_limit() -> None:
    with pytest.raises(ValidationError):
        TradingConfigSchema(history_candles=1501)


def test_default_history_covers_htf_ema_warmup() -> None:
    # 1h EMA50 needs 100 hourly bars = 400 15m candles.
    assert AppConfig.from_env().trading.history_candles >= 400


def test_shipped_yaml_sets_max_margin_ratio_to_the_default() -> None:
    raw = yaml.safe_load((CONFIG_DIR / "config.yaml").read_text(encoding="utf-8"))

    assert raw["risk"]["max_margin_ratio"] == 0.5
    config = AppConfig.from_env()
    assert config.risk.max_margin_ratio == RiskConfigSchema().max_margin_ratio
