"""
Configuration management for KavziTrader.

This module provides classes for managing configuration using Pydantic for validation.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatabaseConfigNested(BaseModel):
    """Configuration for database connection."""

    model_config = ConfigDict(frozen=True)

    dialect: str = Field("postgresql", min_length=1)
    driver: str = Field("asyncpg", min_length=1)
    host: str = Field("localhost", min_length=1)
    port: int = Field(5432, ge=1, le=65535)
    username: str = Field("postgres", min_length=1)
    password: str = Field("postgres", min_length=1)
    database: str = Field("kavzitrader", min_length=1)
    pool_size: int = Field(10, ge=1)
    max_overflow: int = Field(20, ge=0)
    echo: bool = Field(False)
    echo_pool: bool = Field(False)
    options: dict[str, Any] = Field(default_factory=dict)
    url: str = Field("", min_length=0)

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Validate and normalize host."""
        if v == "localhost":
            return "127.0.0.1"
        return v


class BinanceApiConfig(BaseModel):
    """Configuration for Binance API."""

    model_config = ConfigDict(frozen=True)

    api_key: str = Field("", min_length=0)
    api_secret: str = Field("", min_length=0)
    testnet: bool = Field(True)
    use_proxy: bool = Field(False)


class ApiConfig(BaseModel):
    """API configuration container."""

    model_config = ConfigDict(frozen=True)

    binance: BinanceApiConfig


class SystemConfig(BaseModel):
    """System-wide configuration."""

    model_config = ConfigDict(frozen=True)

    data_dir: str = Field("data/")
    models_dir: str = Field("models/")
    results_dir: str = Field("results/")
    timezone: str = Field("UTC")


class AppConfig(BaseModel):
    """Main application configuration."""

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,  # Allow population from aliases
    )

    # Core configuration sections
    system: SystemConfig
    api: ApiConfig
    database: DatabaseConfigNested
    symbols: list[str] = Field(default_factory=list)

    # Hydra default configuration lists
    defaults: list[str | dict[str, str]] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        """
        Create a configuration from a dictionary.

        Args:
            data: Dictionary with configuration values

        Returns:
            Validated AppConfig instance
        """
        return cls.model_validate(data)

    @classmethod
    def from_json(cls, json_file: str | Path) -> "AppConfig":
        """
        Load configuration from a JSON file.

        Args:
            json_file: Path to JSON configuration file

        Returns:
            Validated AppConfig instance
        """
        import json

        with open(json_file) as f:
            data = json.load(f)
        return cls.model_validate(data)

    @classmethod
    def from_yaml(cls, yaml_file: str | Path) -> "AppConfig":
        """
        Load configuration from a YAML file.

        Args:
            yaml_file: Path to YAML configuration file

        Returns:
            Validated AppConfig instance
        """
        import yaml

        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)
