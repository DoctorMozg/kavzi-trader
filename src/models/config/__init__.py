"""
Model configuration for KavziTrader.

This module provides Pydantic schemas for model configuration.
"""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from src.commons.datetime_schema import TimestampedSchema


class ModelConfigSchema(TimestampedSchema):
    """Schema for base model configuration settings."""

    name: Annotated[str, Field(..., min_length=1)]
    version: Annotated[str, Field(..., pattern=r"^\d+\.\d+\.\d+$")]
    description: Annotated[str, Field("")]
    input_size: Annotated[int, Field(..., gt=0)]
    output_size: Annotated[int, Field(..., gt=0)]

    # Training parameters
    batch_size: Annotated[int, Field(32, gt=0)]
    learning_rate: Annotated[float, Field(0.001, gt=0)]
    epochs: Annotated[int, Field(100, gt=0)]
    early_stopping: Annotated[bool, Field(True)]
    patience: Annotated[int, Field(10, ge=0)]
    validation_split: Annotated[float, Field(0.2, ge=0, le=0.5)]

    @classmethod
    def from_file(cls, config_path: Path) -> "ModelConfigSchema":
        """
        Load configuration from a JSON file.

        Args:
            config_path: Path to the configuration file

        Returns:
            Parsed configuration object

        Raises:
            FileNotFoundError: If the configuration file does not exist
            ValueError: If the configuration file is invalid
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path) as f:
                config_data = json.load(f)
            return cls.model_validate(config_data)
        except json.JSONDecodeError as e:
            raise ValueError("Invalid JSON in configuration file") from e
        except Exception as e:
            raise ValueError("Failed to parse configuration file") from e

    def save_to_file(self, config_path: Path) -> None:
        """
        Save configuration to a JSON file.

        Args:
            config_path: Path where the configuration should be saved

        Raises:
            IOError: If the file cannot be written
        """
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)


class TransformerConfigSchema(ModelConfigSchema):
    """Schema for Transformer model configuration.

    The Transformer architecture is the primary model used in KavziTrader
    due to its superior performance for time series prediction tasks.
    """

    d_model: Annotated[int, Field(128, gt=0)]
    nhead: Annotated[int, Field(8, gt=0)]
    num_encoder_layers: Annotated[int, Field(3, gt=0)]
    num_decoder_layers: Annotated[int, Field(3, gt=0)]
    dim_feedforward: Annotated[int, Field(512, gt=0)]
    dropout: Annotated[float, Field(0.1, ge=0, lt=1)]
    activation: Annotated[Literal["relu", "gelu"], Field("relu")]
