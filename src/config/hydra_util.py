"""
Hydra configuration utilities for CLI integration.

This module provides functions to initialize and work with Hydra configurations in the CLI.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, cast

import hydra
from hydra.core.config_store import ConfigStore
from omegaconf import DictConfig, OmegaConf

from src.config import AppConfig

# Initialize logger
logger = logging.getLogger("kavzitrader.config")

# Set default config path - make sure it's relative to the project root
DEFAULT_CONFIG_DIR = "config"
DEFAULT_CONFIG_NAME = "config"

def init_hydra() -> None:
    """Initialize Hydra for the CLI."""
    # Register configuration store if needed
    # This is useful for registering structured configs with Hydra
    cs = ConfigStore.instance()
    # Example: cs.store(name="config_schema", node=AppConfigSchema)


def get_config(config_path: Optional[str] = None, 
               config_name: Optional[str] = None, 
               overrides: Optional[list[str]] = None) -> DictConfig:
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
    
    logger.debug(f"Initializing Hydra with config path: {path}")
    
    # Initialize Hydra with relative path
    hydra.initialize(version_base=None, config_path=Path.cwd().joinpath(path))
    
    # Load configuration with overrides
    cfg = hydra.compose(config_name=name, overrides=overrides)
    logger.debug(f"Loaded configuration from {path}/{name}.yaml")
    
    return cfg


def config_to_dict(config: DictConfig) -> Dict[str, Any]:
    """
    Convert Hydra config to a dictionary.
    
    Args:
        config: Hydra configuration object
        
    Returns:
        Dictionary representation of the config
    """
    return cast(Dict[str, Any], OmegaConf.to_container(config, resolve=True))


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
        app_config = AppConfig.from_dict(config_dict)
        logger.debug("Successfully converted Hydra config to AppConfig")
        return app_config
    except Exception as e:
        logger.error(f"Failed to convert Hydra config to AppConfig: {e}")
        raise


def print_config(config: DictConfig) -> None:
    """
    Print the configuration in a readable format.
    
    Args:
        config: Hydra configuration object
    """
    formatted = OmegaConf.to_yaml(config)
    print("\n=== Configuration ===\n")
    print(formatted)
    print("\n====================\n")


def resolve_relative_paths(config: DictConfig, base_dir: Optional[Path] = None) -> DictConfig:
    """
    Resolve relative paths in the config to absolute paths.
    
    Args:
        config: Hydra configuration object
        base_dir: Base directory for resolving relative paths (default: current directory)
        
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
                if not os.path.isabs(path_value):
                    resolved_config.system[path_field] = str(base / path_value)
    
    return resolved_config 