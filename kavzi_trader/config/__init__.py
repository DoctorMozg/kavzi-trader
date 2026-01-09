"""
Configuration management for KavziTrader.
"""

import os

from pydantic import BaseModel, ConfigDict, Field


class BinanceApiConfig(BaseModel):
    """Configuration for Binance API."""

    model_config = ConfigDict(frozen=True)

    api_key: str = Field("", min_length=0)
    api_secret: str = Field("", min_length=0)
    testnet: bool = Field(True)


class ApiConfig(BaseModel):
    """Configuration for API."""

    model_config = ConfigDict(frozen=True)

    binance: BinanceApiConfig


class SystemConfig(BaseModel):
    """System-wide configuration."""

    model_config = ConfigDict(frozen=True)

    data_dir: str = Field("data/")
    models_dir: str = Field("models/")
    results_dir: str = Field("results/")
    timezone: str = Field("UTC")
    log_level: str = Field("INFO")


class AppConfig(BaseModel):
    """Main application configuration."""

    model_config = ConfigDict(frozen=True)

    system: SystemConfig
    api: ApiConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            system=SystemConfig(
                data_dir=os.getenv("KT_DATA_DIR", "data/"),
                models_dir=os.getenv("KT_MODELS_DIR", "models/"),
                results_dir=os.getenv("KT_RESULTS_DIR", "results/"),
                timezone=os.getenv("KT_TIMEZONE", "UTC"),
                log_level=os.getenv("KT_LOG_LEVEL", "INFO"),
            ),
            api=ApiConfig(
                binance=BinanceApiConfig(
                    api_key=os.getenv("KT_BINANCE_API_KEY", ""),
                    api_secret=os.getenv("KT_BINANCE_API_SECRET", ""),
                    testnet=os.getenv("KT_BINANCE_TESTNET", "true").lower() == "true",
                ),
            ),
        )
