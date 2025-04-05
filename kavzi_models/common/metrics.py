"""
Evaluation metrics for models.

This module provides functions for evaluating model performance,
including regression and classification metrics.
"""

import logging
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)

logger = logging.getLogger(__name__)


def calculate_regression_metrics(
    y_true: Union[np.ndarray, torch.Tensor],
    y_pred: Union[np.ndarray, torch.Tensor],
    sample_weights: Optional[Union[np.ndarray, torch.Tensor]] = None,
) -> Dict[str, float]:
    """
    Calculate regression metrics.
    
    Args:
        y_true: True target values
        y_pred: Predicted target values
        sample_weights: Optional weights for samples
        
    Returns:
        Dictionary of metrics
    """
    # Convert torch tensors to numpy arrays if necessary
    if isinstance(y_true, torch.Tensor):
        y_true = y_true.detach().cpu().numpy()
    if isinstance(y_pred, torch.Tensor):
        y_pred = y_pred.detach().cpu().numpy()
    if sample_weights is not None and isinstance(sample_weights, torch.Tensor):
        sample_weights = sample_weights.detach().cpu().numpy()
    
    # Flatten arrays
    y_true = y_true.flatten()
    y_pred = y_pred.flatten()
    
    # Calculate metrics
    mse = mean_squared_error(y_true, y_pred, sample_weight=sample_weights)
    rmse = np.sqrt(mse)
    mae = mean_absolute_error(y_true, y_pred, sample_weight=sample_weights)
    
    # Calculate MAPE with handling for zero values
    # Add small epsilon to avoid division by zero
    epsilon = 1e-10
    y_true_safe = np.where(np.abs(y_true) < epsilon, epsilon, y_true)
    mape = mean_absolute_percentage_error(y_true_safe, y_pred)
    
    # R² score
    r2 = r2_score(y_true, y_pred, sample_weight=sample_weights)
    
    # Create metrics dictionary
    metrics = {
        "mse": mse,
        "rmse": rmse,
        "mae": mae,
        "mape": mape,
        "r2": r2,
    }
    
    return metrics


def calculate_classification_metrics(
    y_true: Union[np.ndarray, torch.Tensor],
    y_pred: Union[np.ndarray, torch.Tensor],
    threshold: float = 0.5,
    average: str = "weighted",
) -> Dict[str, float]:
    """
    Calculate classification metrics.
    
    Args:
        y_true: True target values
        y_pred: Predicted target values (probabilities)
        threshold: Threshold for binary classification
        average: Averaging method for multiclass metrics
        
    Returns:
        Dictionary of metrics
    """
    # Convert torch tensors to numpy arrays if necessary
    if isinstance(y_true, torch.Tensor):
        y_true = y_true.detach().cpu().numpy()
    if isinstance(y_pred, torch.Tensor):
        y_pred = y_pred.detach().cpu().numpy()
    
    # Apply threshold for binary classification
    y_pred_binary = (y_pred > threshold).astype(int)
    
    # Calculate metrics
    accuracy = accuracy_score(y_true, y_pred_binary)
    precision = precision_score(y_true, y_pred_binary, average=average, zero_division=0)
    recall = recall_score(y_true, y_pred_binary, average=average, zero_division=0)
    f1 = f1_score(y_true, y_pred_binary, average=average, zero_division=0)
    
    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred_binary)
    
    # Create metrics dictionary
    metrics = {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": cm,
    }
    
    return metrics


def calculate_directional_accuracy(
    y_true: Union[np.ndarray, torch.Tensor],
    y_pred: Union[np.ndarray, torch.Tensor],
) -> float:
    """
    Calculate directional accuracy (for price movement prediction).
    
    This metric measures how often the model correctly predicts
    the direction of movement (up or down), regardless of magnitude.
    
    Args:
        y_true: True target values
        y_pred: Predicted target values
        
    Returns:
        Directional accuracy (0.0 to 1.0)
    """
    # Convert torch tensors to numpy arrays if necessary
    if isinstance(y_true, torch.Tensor):
        y_true = y_true.detach().cpu().numpy()
    if isinstance(y_pred, torch.Tensor):
        y_pred = y_pred.detach().cpu().numpy()
    
    # Get direction of movement
    y_true_direction = np.sign(y_true)
    y_pred_direction = np.sign(y_pred)
    
    # Calculate accuracy
    correct = (y_true_direction == y_pred_direction).sum()
    total = len(y_true)
    
    return float(correct) / total


def calculate_profit_factor(
    y_true: Union[np.ndarray, torch.Tensor],
    y_pred: Union[np.ndarray, torch.Tensor],
    threshold: float = 0.0,
) -> float:
    """
    Calculate profit factor based on predictions.
    
    Profit factor is the ratio of the sum of all profitable trades
    to the sum of all losing trades. A profit factor > 1 indicates
    an overall profitable strategy.
    
    Args:
        y_true: True target values (returns)
        y_pred: Predicted target values
        threshold: Threshold for taking trades
        
    Returns:
        Profit factor
    """
    # Convert torch tensors to numpy arrays if necessary
    if isinstance(y_true, torch.Tensor):
        y_true = y_true.detach().cpu().numpy()
    if isinstance(y_pred, torch.Tensor):
        y_pred = y_pred.detach().cpu().numpy()
    
    # Generate trade signals based on predictions and threshold
    signals = np.sign(y_pred - threshold)
    
    # Calculate returns for each trade
    trade_returns = signals * y_true
    
    # Separate winning and losing trades
    winning_trades = trade_returns[trade_returns > 0]
    losing_trades = trade_returns[trade_returns < 0]
    
    # Calculate profit factor
    total_profits = winning_trades.sum() if len(winning_trades) > 0 else 0
    total_losses = abs(losing_trades.sum()) if len(losing_trades) > 0 else 0
    
    # Avoid division by zero
    if total_losses == 0:
        return float('inf') if total_profits > 0 else 0.0
    
    return float(total_profits) / total_losses


def log_metrics(
    metrics: Dict[str, Union[float, np.ndarray]],
    prefix: str = "",
    level: str = "info",
) -> None:
    """
    Log metrics with appropriate formatting.
    
    Args:
        metrics: Dictionary of metrics to log
        prefix: Prefix to add to metric names
        level: Logging level (info, debug, warning, error)
    """
    log_func = getattr(logger, level)
    
    for name, value in metrics.items():
        # Skip non-scalar metrics like confusion matrices
        if isinstance(value, np.ndarray) and value.ndim > 0:
            continue
        
        metric_name = f"{prefix}{name}" if prefix else name
        log_func(f"{metric_name}: {value:.4f}") 