"""
Transformer model architecture for price forecasting.

This module implements a transformer-based model for
predicting price movements of crypto assets.
"""

import logging
from typing import Dict, List, Optional, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from kavzi_models.forecaster.config import ForecasterConfig, ModelConfig

logger = logging.getLogger(__name__)


class PositionalEncoding(nn.Module):
    """
    Positional encoding for transformer model.
    
    Adds positional information to input embeddings
    to provide sequential context for the transformer.
    """
    
    def __init__(
        self,
        d_model: int,
        max_seq_len: int = 5000,
        dropout: float = 0.1,
    ) -> None:
        """
        Initialize positional encoding.
        
        Args:
            d_model: Embedding dimension
            max_seq_len: Maximum sequence length
            dropout: Dropout rate
        """
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        # Create positional encoding matrix
        pe = torch.zeros(max_seq_len, d_model)
        position = torch.arange(0, max_seq_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-torch.log(torch.tensor(10000.0)) / d_model)
        )
        
        # Apply sine to even indices and cosine to odd indices
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        # Add batch dimension and register as buffer (not a parameter)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)
    
    def forward(self, x: Tensor) -> Tensor:
        """
        Add positional encoding to input embeddings.
        
        Args:
            x: Input tensor of shape [batch_size, seq_len, d_model]
            
        Returns:
            Tensor with positional encoding added
        """
        x = x + self.pe[:, :x.size(1)]
        return self.dropout(x)


class TimeSeriesTransformerEncoder(nn.Module):
    """
    Transformer encoder for time series data.
    
    Uses multi-head attention to process sequential data
    and capture temporal relationships.
    """
    
    def __init__(
        self,
        input_dim: int,
        d_model: int = 128,
        n_heads: int = 8,
        n_layers: int = 4,
        d_ff: int = 256,
        dropout: float = 0.1,
        activation: str = "gelu",
    ) -> None:
        """
        Initialize transformer encoder.
        
        Args:
            input_dim: Dimension of input features
            d_model: Embedding dimension
            n_heads: Number of attention heads
            n_layers: Number of transformer layers
            d_ff: Dimension of feedforward network
            dropout: Dropout rate
            activation: Activation function in transformer
        """
        super().__init__()
        
        # Feature projection
        self.feature_projection = nn.Linear(input_dim, d_model)
        
        # Positional encoding
        self.pos_encoding = PositionalEncoding(d_model, dropout=dropout)
        
        # Create transformer encoder layer
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_ff,
            dropout=dropout,
            activation=activation,
            batch_first=True,
        )
        
        # Create the encoder with n_layers
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=n_layers,
        )
        
        # Initialize parameters
        self._init_parameters()
    
    def _init_parameters(self) -> None:
        """Initialize model parameters."""
        for name, p in self.named_parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)
    
    def forward(
        self,
        x: Tensor,
        src_mask: Optional[Tensor] = None,
    ) -> Tensor:
        """
        Process time series data through transformer encoder.
        
        Args:
            x: Input tensor of shape [batch_size, seq_len, input_dim]
            src_mask: Optional mask for padded elements
            
        Returns:
            Encoded representation of shape [batch_size, seq_len, d_model]
        """
        # Project input features to embedding dimension
        x = self.feature_projection(x)
        
        # Add positional encoding
        x = self.pos_encoding(x)
        
        # Pass through transformer encoder
        output = self.transformer_encoder(x, src_mask)
        
        return output


class TimeSeriesForecaster(nn.Module):
    """
    Complete transformer model for time series forecasting.
    
    Combines transformer encoder with regression head for
    price movement prediction.
    """
    
    def __init__(
        self,
        config: ModelConfig,
        input_dim: int,
        output_dim: int = 1,
    ) -> None:
        """
        Initialize forecaster model.
        
        Args:
            config: Model configuration
            input_dim: Number of input features
            output_dim: Number of output dimensions
        """
        super().__init__()
        
        self.config = config
        self.input_dim = input_dim
        self.output_dim = output_dim
        
        # Transformer encoder
        self.encoder = TimeSeriesTransformerEncoder(
            input_dim=input_dim,
            d_model=config.d_model,
            n_heads=config.n_heads,
            n_layers=config.n_layers,
            d_ff=config.d_ff,
            dropout=config.dropout,
            activation=config.activation,
        )
        
        # Regression output head
        if config.prediction_type == "regression":
            # For single point prediction
            self.output_head = nn.Linear(config.d_model, output_dim)
        
        elif config.prediction_type == "quantile":
            # For quantile regression
            self.output_head = nn.Linear(config.d_model, len(config.quantiles))
        
        else:
            raise ValueError(f"Unknown prediction type: {config.prediction_type}")
        
        # Initialize parameters
        self._init_parameters()
    
    def _init_parameters(self) -> None:
        """Initialize model parameters for output layers."""
        for name, p in self.output_head.named_parameters():
            if "bias" in name:
                nn.init.zeros_(p)
            elif "weight" in name:
                nn.init.xavier_uniform_(p)
    
    def forward(self, x: Tensor) -> Tensor:
        """
        Forward pass through the forecaster model.
        
        Args:
            x: Input tensor of shape [batch_size, seq_len, input_dim]
            
        Returns:
            Predictions tensor of shape [batch_size, output_dim]
        """
        # Pass through transformer encoder
        # Shape: [batch_size, seq_len, d_model]
        encoded = self.encoder(x)
        
        # Get the last time step representation
        # Shape: [batch_size, d_model]
        last_hidden = encoded[:, -1, :]
        
        # Apply output head
        # Shape: [batch_size, output_dim]
        output = self.output_head(last_hidden)
        
        # Apply activation for output if specified
        if self.config.output_activation == "sigmoid":
            output = torch.sigmoid(output)
        elif self.config.output_activation == "tanh":
            output = torch.tanh(output)
        
        return output
    
    def predict(
        self,
        x: Tensor,
        return_confidence: bool = False,
    ) -> Union[Tensor, Tuple[Tensor, Tensor]]:
        """
        Make predictions with optional confidence intervals.
        
        Args:
            x: Input tensor
            return_confidence: Whether to return confidence intervals
            
        Returns:
            Predictions tensor or tuple of (predictions, confidence)
        """
        self.eval()
        with torch.no_grad():
            output = self.forward(x)
            
            if return_confidence and self.config.prediction_type == "quantile":
                # For quantile regression, separate predictions
                # Middle quantile is the point prediction, others form CI
                median_idx = len(self.config.quantiles) // 2
                prediction = output[:, median_idx].unsqueeze(1)
                confidence = output  # All quantiles
                
                return prediction, confidence
            
            return output


def create_forecaster_model(
    config: ForecasterConfig,
    input_dim: int,
    output_dim: int = 1,
) -> TimeSeriesForecaster:
    """
    Create a forecaster model instance.
    
    Args:
        config: Complete forecaster configuration
        input_dim: Number of input features
        output_dim: Number of output dimensions
        
    Returns:
        Initialized TimeSeriesForecaster
    """
    logger.info(f"Creating forecaster model with {input_dim} input features")
    
    # Set device
    device = torch.device(config.training.device if torch.cuda.is_available() else "cpu")
    
    # Create model
    model = TimeSeriesForecaster(
        config=config.model,
        input_dim=input_dim,
        output_dim=output_dim,
    )
    
    # Move to device
    model = model.to(device)
    
    # Count parameters
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    
    logger.info(f"Model created with {total_params:,} parameters ({trainable_params:,} trainable)")
    
    return model 