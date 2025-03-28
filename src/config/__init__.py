"""
Configuration management for KavziTrader.

This module provides classes for managing configuration using Pydantic for validation.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DatabaseConfig(BaseModel):
    """Configuration for database connection."""

    model_config = ConfigDict(frozen=True)

    host: str = Field(..., min_length=1)
    port: int = Field(5432, ge=1, le=65535)
    database: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    ssl_mode: Literal["disable", "require", "verify-ca", "verify-full"] = "disable"

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

    api_key: str = Field(..., min_length=1)
    api_secret: str = Field(..., min_length=1)
    use_testnet: bool = Field(False)
    timeout_ms: int = Field(5000, ge=1000)


class ModelConfig(BaseModel):
    """Configuration for model training and inference."""

    model_config = ConfigDict(frozen=True)

    type: Literal["lstm", "transformer", "cnn"] = "lstm"
    hidden_size: int = Field(64, ge=1)
    num_layers: int = Field(2, ge=1)
    dropout: float = Field(0.2, ge=0.0, le=1.0)
    learning_rate: float = Field(0.001, gt=0.0)
    batch_size: int = Field(32, ge=1)
    max_epochs: int = Field(100, ge=1)
    early_stopping_patience: int = Field(10, ge=0)

    @model_validator(mode="after")
    def validate_model_params(self) -> "ModelConfig":
        """Validate model-specific parameters."""
        if self.type == "transformer" and self.hidden_size % 8 != 0:
            raise ValueError(
                "For transformer models, hidden_size must be a multiple of 8",
            )
        return self


class AppConfig(BaseModel):
    """Main application configuration."""

    model_config = ConfigDict(frozen=True)

    database: DatabaseConfig
    binance_api: BinanceApiConfig
    models: dict[str, ModelConfig]  # Model name to config mapping
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_dir: Path = Path("./data")
    models_dir: Path = Path("./models")

    @field_validator("data_dir", "models_dir")
    @classmethod
    def validate_directory(cls, v: Path) -> Path:
        """Validate directory paths and ensure they exist."""
        v.mkdir(parents=True, exist_ok=True)
        return v.resolve()

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
