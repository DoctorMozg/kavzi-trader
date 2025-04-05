"""
Configuration for the forecaster model.

This module defines Pydantic models for configuration
and default values for the price movement forecasting model.
Designed to be compatible with Hydra configuration system.
"""

from pathlib import Path
from typing import Annotated, List, Optional, Union

from pydantic import BaseModel, Field

from kavzi_trader.commons.datetime_schema import DateTimeWithTimezoneSchema


class DataConfig(BaseModel):
    """Data configuration for the forecaster model."""
    
    # Time series parameters
    window_size: Annotated[int, Field(description="Number of time steps in input window")] = 30
    forecast_horizon: Annotated[int, Field(description="Number of time steps to predict ahead")] = 1
    stride: Annotated[int, Field(description="Step size for sliding window")] = 1
    
    # Feature selection
    price_features: Annotated[List[str], Field(description="Price-related features to use")] = [
        "open", "high", "low", "close", "volume"
    ]
    technical_indicators: Annotated[List[str], Field(description="Technical indicators to include")] = [
        "rsi", "macd", "macd_signal", "macd_hist", 
        "bb_upper", "bb_middle", "bb_lower",
        "atr", "adx"
    ]
    target_column: Annotated[str, Field(description="Target column to predict")] = "close"
    
    # Data normalization
    normalization_method: Annotated[str, Field(description="Method for normalizing features")] = "zscore"
    
    # Dataset splitting
    val_size: Annotated[float, Field(description="Validation set size", ge=0.0, le=0.5)] = 0.15
    test_size: Annotated[float, Field(description="Test set size", ge=0.0, le=0.5)] = 0.15
    time_based_split: Annotated[bool, Field(description="Use time-based splitting instead of random")] = True
    
    # Data paths
    data_dir: Annotated[str, Field(description="Directory for data storage")] = "data"
    cache_dir: Annotated[str, Field(description="Directory for cached datasets")] = "data/cache"


class ModelConfig(BaseModel):
    """Model configuration for the forecaster model."""
    
    # Model architecture
    d_model: Annotated[int, Field(description="Embedding dimension")] = 128
    n_heads: Annotated[int, Field(description="Number of attention heads")] = 8
    n_layers: Annotated[int, Field(description="Number of transformer layers")] = 4
    d_ff: Annotated[int, Field(description="Dimension of feedforward network")] = 256
    dropout: Annotated[float, Field(description="Dropout rate", ge=0.0, le=0.9)] = 0.1
    
    # Activation functions
    activation: Annotated[str, Field(description="Activation function in transformer")] = "gelu"
    
    # Output head configuration
    prediction_type: Annotated[str, Field(description="Type of prediction task")] = "regression"
    output_activation: Annotated[Optional[str], Field(description="Activation for output layer")] = None
    quantiles: Annotated[List[float], Field(description="Quantiles for quantile regression")] = [0.1, 0.5, 0.9]


class TrainingConfig(BaseModel):
    """Training configuration for the forecaster model."""
    
    # Basic training parameters
    batch_size: Annotated[int, Field(description="Batch size for training")] = 64
    learning_rate: Annotated[float, Field(description="Learning rate")] = 1e-4
    weight_decay: Annotated[float, Field(description="Weight decay for regularization")] = 1e-6
    max_epochs: Annotated[int, Field(description="Maximum number of training epochs")] = 100
    early_stopping_patience: Annotated[int, Field(description="Patience for early stopping")] = 10
    
    # Optimizer settings
    optimizer: Annotated[str, Field(description="Optimizer type")] = "adam"
    lr_scheduler: Annotated[str, Field(description="Learning rate scheduler type")] = "cosine"
    
    # Loss function
    loss_fn: Annotated[str, Field(description="Loss function")] = "mse"
    
    # Device settings
    device: Annotated[str, Field(description="Device for training")] = "cuda"
    precision: Annotated[str, Field(description="Precision for training")] = "float32"
    
    # Checkpointing
    checkpoint_dir: Annotated[str, Field(description="Directory for model checkpoints")] = "models/checkpoints"
    save_top_k: Annotated[int, Field(description="Number of best models to save")] = 2
    
    # Logging
    log_dir: Annotated[str, Field(description="Directory for logs")] = "logs"
    log_every_n_steps: Annotated[int, Field(description="Frequency of logging")] = 50


class ForecasterConfig(BaseModel):
    """Complete configuration for the forecaster model."""
    
    # Component configurations
    data: Annotated[DataConfig, Field(description="Data configuration")] = DataConfig()
    model: Annotated[ModelConfig, Field(description="Model architecture configuration")] = ModelConfig()
    training: Annotated[TrainingConfig, Field(description="Training configuration")] = TrainingConfig()
    
    # General settings
    experiment_name: Annotated[str, Field(description="Name for the experiment")] = "forecaster_base"
    seed: Annotated[int, Field(description="Random seed for reproducibility")] = 42
    
    # Default model paths
    model_save_path: Annotated[str, Field(description="Path to save the final model")] = "models/forecaster"
    
    def initialize_directories(self) -> None:
        """Initialize directory paths."""
        # Create directories if they don't exist
        for path in [
            self.data.data_dir,
            self.data.cache_dir,
            self.training.checkpoint_dir,
            self.training.log_dir,
            self.model_save_path,
        ]:
            Path(path).mkdir(parents=True, exist_ok=True)


# This is used by Hydra for configuration
def get_config() -> ForecasterConfig:
    """
    Get default configuration.
    
    This function is used by Hydra to initialize the configuration.
    Returns:
        Default ForecasterConfig instance
    """
    return ForecasterConfig() 