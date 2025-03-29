"""
Hydra configuration utilities for CLI integration.

This module provides functions to initialize and
work with Hydra configurations in the CLI.
"""

import logging
from pathlib import Path
from typing import Any, cast

import hydra
from hydra.core.config_store import ConfigStore
from omegaconf import DictConfig, OmegaConf

from src.config import AppConfig

# Initialize logger
logger = logging.getLogger("kavzitrader.config")

# Set default config path - make sure it's relative to the project root
DEFAULT_CONFIG_DIR = "./config"
DEFAULT_CONFIG_NAME = "config"


def init_hydra() -> None:
    """Initialize Hydra for the CLI."""
    # Register configuration store if needed
    # This is useful for registering structured configs with Hydra
    ConfigStore.instance()
    # Example is : cs.store(name="config_schema", node=AppConfigSchema)


def get_config(
    config_path: str | None = None,
    config_name: str | None = None,
    overrides: list[str] | None = None,
) -> DictConfig:
    """
    Get Hydra configuration with optional overrides.

    Args:
        config_path: Path to config directory
        config_name: Name of the config file (without extension)
        overrides: List of Hydra overrides (e.g. ["training.lr=0.01"])

    Returns:
        Hydra configuration object
    """
    # Use provided or default paths
    path = config_path or DEFAULT_CONFIG_DIR
    name = config_name or DEFAULT_CONFIG_NAME
    overrides = overrides or []

    config_path_joined = Path("./../../").joinpath(path)

    logger.debug(f"Initializing Hydra with config path: {config_path_joined}")

    # Initialize Hydra with relative path
    hydra.initialize(version_base=None, config_path=str(config_path_joined))

    # Load configuration with overrides
    cfg = hydra.compose(config_name=name, overrides=overrides)
    logger.debug(f"Loaded configuration from {config_path_joined}/{name}.yaml")

    return cfg


def config_to_dict(config: DictConfig) -> dict[str, Any]:
    """
    Convert Hydra config to a dictionary.

    Args:
        config: Hydra configuration object

    Returns:
        Dictionary representation of the config
    """
    return cast(dict[str, Any], OmegaConf.to_container(config, resolve=True))


def config_to_app_config(config: DictConfig) -> AppConfig:
    """
    Convert Hydra config to AppConfig Pydantic model.

    Args:
        config: Hydra configuration object

    Returns:
        AppConfig instance with validated configuration
    """
    # First resolve all variables and convert to dict
    config_dict = config_to_dict(config)

    # Convert to AppConfig
    try:
        app_config = AppConfig.model_validate(config_dict)
        logger.debug("Successfully converted Hydra config to AppConfig")
    except Exception:
        logger.exception("Failed to convert Hydra config to AppConfig")
        raise
    else:
        return app_config


def print_config(config: DictConfig) -> None:
    """
    Print the configuration in a readable format.

    Args:
        config: Hydra configuration object
    """
    formatted = OmegaConf.to_yaml(config)
    logger.info("\n=== Configuration ===\n")
    logger.info(formatted)
    logger.info("\n====================\n")


def resolve_relative_paths(
    config: DictConfig,
    base_dir: Path | None = None,
) -> DictConfig:
    """
    Resolve relative paths in the config to absolute paths.

    Args:
        config: Hydra configuration object
        base_dir: Base directory for resolving relative paths

    Returns:
        Configuration with resolved paths
    """
    base = base_dir or Path.cwd()

    # Create a copy of the config to avoid modifying the original
    resolved_config = OmegaConf.create(OmegaConf.to_container(config, resolve=True))

    # Process specified path fields in the config
    if "system" in resolved_config:
        for path_field in ["data_dir", "models_dir", "results_dir"]:
            if path_field in resolved_config.system:
                path_value = resolved_config.system[path_field]
                if not Path(path_value).is_absolute():
                    resolved_config.system[path_field] = str(base / path_value)

    return resolved_config
