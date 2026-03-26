"""
Configuration management for KavziTrader.
"""

import os
from pathlib import Path
from typing import Annotated, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from kavzi_trader.brain.config import BrainConfigSchema
from kavzi_trader.events.config import EventStoreConfigSchema
from kavzi_trader.orchestrator.config import OrchestratorConfigSchema
from kavzi_trader.paper.config import PaperTradingConfigSchema
from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.state.config import RedisConfigSchema
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


class BinanceApiConfigSchema(BaseModel):
    """Configuration for Binance API."""

    api_key: Annotated[str, Field(default="")]
    api_secret: Annotated[str, Field(default="")]
    testnet: Annotated[bool, Field(default=True)]
    use_proxy: Annotated[bool, Field(default=False)]

    model_config = ConfigDict(frozen=True)


class ApiConfigSchema(BaseModel):
    """Configuration for API providers."""

    binance: Annotated[BinanceApiConfigSchema, Field(...)]

    model_config = ConfigDict(frozen=True)


class SystemConfigSchema(BaseModel):
    """System-wide configuration."""

    data_dir: Annotated[Path, Field(default=Path("data"))]
    models_dir: Annotated[Path, Field(default=Path("models"))]
    results_dir: Annotated[Path, Field(default=Path("results"))]
    timezone: Annotated[str, Field(default="UTC")]

    model_config = ConfigDict(frozen=True)


VALID_INTERVALS = frozenset(
    {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"},
)


class TradingConfigSchema(BaseModel):
    """Trading universe configuration."""

    symbols: Annotated[list[str], Field(default_factory=list)]
    interval: Annotated[str, Field(default="1m")]
    history_candles: Annotated[int, Field(default=1000, ge=1)]

    model_config = ConfigDict(frozen=True)

    @field_validator("interval")
    @classmethod
    def _interval_valid(cls, v: str) -> str:
        if v not in VALID_INTERVALS:
            msg = "trading.interval must be one of %s" % VALID_INTERVALS
            raise ValueError(msg)
        return v


class OrderFlowConfigSchema(BaseModel):
    """Order flow fetch and threshold settings."""

    funding_extreme_threshold: Annotated[float, Field(default=2.0)]

    model_config = ConfigDict(frozen=True)


class MonitoringConfigSchema(BaseModel):
    """Monitoring and logging configuration."""

    log_format: Annotated[str, Field(default="json")]
    log_level: Annotated[str, Field(default="DEBUG")]
    decision_log_enabled: Annotated[bool, Field(default=True)]
    decision_log_retention_days: Annotated[int, Field(default=30, ge=1)]
    metrics_enabled: Annotated[bool, Field(default=True)]

    model_config = ConfigDict(frozen=True)


class ReportingConfigSchema(BaseModel):
    """HTML report generation configuration."""

    enabled: Annotated[bool, Field(default=True)]
    report_dir: Annotated[Path, Field(default=Path("results/reports"))]
    refresh_interval_s: Annotated[int, Field(default=3, ge=1)]
    max_action_entries: Annotated[int, Field(default=500, ge=10)]
    max_trade_entries: Annotated[int, Field(default=200, ge=10)]

    model_config = ConfigDict(frozen=True)


class AppConfig(BaseModel):
    """Main application configuration."""

    system: Annotated[SystemConfigSchema, Field(...)]
    api: Annotated[ApiConfigSchema, Field(...)]
    brain: Annotated[BrainConfigSchema, Field(default_factory=BrainConfigSchema)]
    trading: Annotated[TradingConfigSchema, Field(...)]
    risk: Annotated[RiskConfigSchema, Field(...)]
    position_management: Annotated[PositionManagementConfigSchema, Field(...)]
    order_flow: Annotated[OrderFlowConfigSchema, Field(...)]
    filters: Annotated[FilterConfigSchema, Field(...)]
    redis: Annotated[RedisConfigSchema, Field(...)]
    execution: Annotated[ExecutionConfigSchema, Field(...)]
    events: Annotated[EventStoreConfigSchema, Field(...)]
    orchestrator: Annotated[OrchestratorConfigSchema, Field(...)]
    monitoring: Annotated[MonitoringConfigSchema, Field(...)]
    reporting: Annotated[
        ReportingConfigSchema,
        Field(default_factory=ReportingConfigSchema),
    ]
    paper: Annotated[PaperTradingConfigSchema, Field(...)]

    model_config = ConfigDict(frozen=True)

    def validate_for_trading(self) -> None:
        """Raise if config is insufficient for live trading."""
        errors: list[str] = []
        if not self.api.binance.api_key:
            errors.append(
                "KT_BINANCE_API_KEY (or api.binance.api_key) is required",
            )
        if not self.api.binance.api_secret:
            errors.append(
                "KT_BINANCE_API_SECRET (or api.binance.api_secret)"
                " is required",
            )
        if not self.brain.openrouter_api_key:
            errors.append(
                "KT_OPENROUTER_API_KEY (or brain.openrouter_api_key)"
                " is required",
            )
        if not self.trading.symbols:
            errors.append(
                "trading.symbols must contain at least one symbol",
            )
        if errors:
            raise ValueError(
                "Configuration errors:\n  - " + "\n  - ".join(errors),
            )

    def validate_for_paper_trading(self) -> None:
        """Raise if config is insufficient for paper trading."""
        errors: list[str] = []
        if not self.brain.openrouter_api_key:
            errors.append(
                "KT_OPENROUTER_API_KEY (or brain.openrouter_api_key)"
                " is required",
            )
        if not self.trading.symbols:
            errors.append(
                "trading.symbols must contain at least one symbol",
            )
        if errors:
            raise ValueError(
                "Paper trading configuration errors:\n  - "
                + "\n  - ".join(errors),
            )

    @classmethod
    def from_file(cls, path: Path) -> "AppConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cls._apply_env_overrides(data)
        return cls.model_validate(data)

    @classmethod
    def from_env(cls) -> "AppConfig":
        config_path = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
        return cls.from_file(config_path)

    @classmethod
    def _apply_env_overrides(cls, data: dict[str, object]) -> None:
        api = cast(dict[str, object], data.setdefault("api", {}))
        binance = cast(dict[str, object], api.setdefault("binance", {}))
        env_api_key = os.getenv("KT_BINANCE_API_KEY")
        env_api_secret = os.getenv("KT_BINANCE_API_SECRET")
        env_testnet = os.getenv("KT_BINANCE_TESTNET")
        if env_api_key is not None:
            binance["api_key"] = env_api_key
        if env_api_secret is not None:
            binance["api_secret"] = env_api_secret
        if env_testnet is not None:
            binance["testnet"] = env_testnet.lower() == "true"

        brain = cast(dict[str, object], data.setdefault("brain", {}))
        env_openrouter_key = os.getenv("KT_OPENROUTER_API_KEY")
        if env_openrouter_key is not None:
            brain["openrouter_api_key"] = env_openrouter_key
