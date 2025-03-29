"""
Configuration management for KavziTrader.

This module provides classes for managing configuration using Pydantic for validation.
"""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatabaseConfigNested(BaseModel):
    """Configuration for database connection."""

    model_config = ConfigDict(frozen=True)

    dialect: str = Field("postgresql", min_length=1)
    driver: str = Field("psycopg2", min_length=1)
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

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Validate and normalize host."""
        if v == "localhost":
            return "127.0.0.1"
        return v


class DatabaseConfig(BaseModel):
    """Database configuration container."""

    model_config = ConfigDict(frozen=True)

    database: DatabaseConfigNested


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


class LoggingConfigNested(BaseModel):
    """Configuration for logging."""

    model_config = ConfigDict(frozen=True)

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: str = Field("%(levelname)s: %(message)s", min_length=1)
    date_format: str = Field("%Y-%m-%d %H:%M:%S", min_length=1)
    file: str | None = None
    console: bool = Field(True)


class LoggingConfig(BaseModel):
    """Logging configuration container."""

    model_config = ConfigDict(frozen=True)

    logging: LoggingConfigNested


class CleaningConfig(BaseModel):
    """Data cleaning configuration."""

    model_config = ConfigDict(frozen=True)

    remove_outliers: bool = Field(True)
    outlier_std_threshold: float = Field(3.0, gt=0.0)
    fill_missing: bool = Field(True)
    fill_method: Literal["ffill", "bfill", "interpolate", "zero"] = "ffill"


class NormalizationConfig(BaseModel):
    """Data normalization configuration."""

    model_config = ConfigDict(frozen=True)

    method: Literal["standard", "minmax", "robust", "none"] = "standard"
    feature_range: Annotated[list[float], Field([-1, 1], min_length=2, max_length=2)]


class SequenceConfig(BaseModel):
    """Sequence preparation configuration."""

    model_config = ConfigDict(frozen=True)

    window_size: int = Field(60, ge=1)
    forecast_horizon: int = Field(1, ge=1)
    stride: int = Field(1, ge=1)


class FeatureSelectionConfig(BaseModel):
    """Feature selection configuration."""

    model_config = ConfigDict(frozen=True)

    include_raw: bool = Field(True)
    include_technical: bool = Field(True)
    include_derived: bool = Field(True)


class SplitConfig(BaseModel):
    """Data split configuration."""

    model_config = ConfigDict(frozen=True)

    train_ratio: float = Field(0.7, gt=0.0, lt=1.0)
    val_ratio: float = Field(0.15, ge=0.0, lt=1.0)
    test_ratio: float = Field(0.15, ge=0.0, lt=1.0)
    shuffle: bool = Field(False)
    gap_days: int = Field(1, ge=0)


class PreprocessingNestedConfig(BaseModel):
    """Nested preprocessing configuration."""

    model_config = ConfigDict(frozen=True)

    cleaning: CleaningConfig
    normalization: NormalizationConfig
    sequence: SequenceConfig
    features: FeatureSelectionConfig
    split: SplitConfig


class PreprocessingConfig(BaseModel):
    """Preprocessing configuration container."""

    model_config = ConfigDict(frozen=True)

    preprocessing: PreprocessingNestedConfig


class TechnicalIndicator(BaseModel):
    """Technical indicator configuration."""

    model_config = ConfigDict(frozen=True)

    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class CustomFeature(BaseModel):
    """Custom feature configuration."""

    model_config = ConfigDict(frozen=True)

    name: str
    formula: str


class TransformationConfig(BaseModel):
    """Feature transformation configuration."""

    model_config = ConfigDict(frozen=True)

    normalization: str = Field("standard_scaler")
    scaling: bool = Field(True)
    log_transform: bool = Field(False)


class SelectionConfig(BaseModel):
    """Feature selection configuration."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(False)
    method: str = Field("variance_threshold")
    threshold: float = Field(0.01, ge=0.0)


class FeaturesNestedConfig(BaseModel):
    """Nested features configuration."""

    model_config = ConfigDict(frozen=True)

    technical_indicators: list[TechnicalIndicator]
    custom_features: list[CustomFeature]
    transformations: TransformationConfig
    selection: SelectionConfig


class FeaturesConfig(BaseModel):
    """Features configuration container."""

    model_config = ConfigDict(frozen=True)

    features: FeaturesNestedConfig


class SystemConfig(BaseModel):
    """System-wide configuration."""

    model_config = ConfigDict(frozen=True)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_dir: str = Field("data/")
    models_dir: str = Field("models/")
    results_dir: str = Field("results/")
    timezone: str = Field("UTC")


class DataConfig(BaseModel):
    """Configuration for data collection and processing."""

    model_config = ConfigDict(frozen=True)

    intervals: list[str]
    default_interval: str
    max_historical_days: int = Field(365, ge=1)
    update_frequency: int = Field(60, gt=0)  # in seconds
    preprocessing: PreprocessingConfig | None = None
    features: FeaturesConfig | None = None


class AppConfig(BaseModel):
    """Main application configuration."""

    model_config = ConfigDict(frozen=True)

    # Core configuration sections
    system: SystemConfig
    api: ApiConfig
    symbols: list[str]
    data: DataConfig

    # These are added by Hydra
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
