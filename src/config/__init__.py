"""
Configuration management for KavziTrader.

This module provides classes for managing configuration using Pydantic for validation.
"""

import os

from pydantic import BaseModel, ConfigDict, Field


class DatabaseConfig(BaseModel):
    """Configuration for database connection."""

    model_config = ConfigDict(frozen=True)

    dialect: str = Field("postgresql", min_length=1)
    driver: str = Field("asyncpg", min_length=1)
    host: str = Field("127.0.0.1", min_length=1)
    port: int = Field(5432, ge=1, le=65535)
    username: str = Field("postgres", min_length=1)
    password: str = Field("postgres", min_length=1)
    database: str = Field("kavzitrader", min_length=1)
    pool_size: int = Field(10, ge=1)
    max_overflow: int = Field(20, ge=0)
    echo: bool = Field(False)
    echo_pool: bool = Field(False)
    connect_timeout: int = Field(10, ge=0)
    client_encoding: str = Field("utf8", min_length=1)
    application_name: str = Field("kavzitrader", min_length=1)

    @property
    def url(self) -> str:
        """Generate database URL from components."""
        return f"{self.dialect}+{self.driver}://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


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
    database: DatabaseConfig
    api: ApiConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Create AppConfig from environment variables with KT_ prefix."""
        return cls(
            system=SystemConfig(
                data_dir=os.getenv("KT_DATA_DIR", "data/"),
                models_dir=os.getenv("KT_MODELS_DIR", "models/"),
                results_dir=os.getenv("KT_RESULTS_DIR", "results/"),
                timezone=os.getenv("KT_TIMEZONE", "UTC"),
                log_level=os.getenv("KT_LOG_LEVEL", "INFO"),
            ),
            database=DatabaseConfig(
                host=os.getenv("KT_DB_HOST", "127.0.0.1"),
                port=int(os.getenv("KT_DB_PORT", "5432")),
                username=os.getenv("KT_DB_USER", "postgres"),
                password=os.getenv("KT_DB_PASSWORD", "postgres"),
                database=os.getenv("KT_DB_NAME", "kavzitrader"),
                pool_size=int(os.getenv("KT_DB_POOL_SIZE", "10")),
                max_overflow=int(os.getenv("KT_DB_MAX_OVERFLOW", "20")),
                echo=os.getenv("KT_DB_ECHO", "false").lower() == "true",
                echo_pool=os.getenv("KT_DB_ECHO_POOL", "false").lower() == "true",
                connect_timeout=int(os.getenv("KT_DB_CONNECT_TIMEOUT", "10")),
                client_encoding=os.getenv("KT_DB_CLIENT_ENCODING", "utf8"),
                application_name=os.getenv("KT_DB_APPLICATION_NAME", "kavzitrader"),
            ),
            api=ApiConfig(
                binance=BinanceApiConfig(
                    api_key=os.getenv("KT_BINANCE_API_KEY", ""),
                    api_secret=os.getenv("KT_BINANCE_API_SECRET", ""),
                    testnet=os.getenv("KT_BINANCE_TESTNET", "true").lower() == "true",
                ),
            ),
        )
