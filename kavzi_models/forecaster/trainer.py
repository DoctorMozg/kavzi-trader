"""
Training pipeline for the forecaster model.

This module implements the training loop, evaluation,
and model saving/loading functionality.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any, Callable

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.optim.lr_scheduler import (
    CosineAnnealingLR,
    ReduceLROnPlateau,
    StepLR,
)

from kavzi_models.common.metrics import (
    calculate_regression_metrics,
    calculate_directional_accuracy,
    calculate_profit_factor,
    log_metrics,
)
from kavzi_models.forecaster.config import ForecasterConfig
from kavzi_models.forecaster.model import TimeSeriesForecaster

logger = logging.getLogger(__name__)


class EarlyStopping:
    """
    Early stopping to halt training when validation performance stops improving.
    """
    
    def __init__(
        self,
        patience: int = 10,
        min_delta: float = 0.0,
        mode: str = "min",
    ) -> None:
        """
        Initialize early stopping.
        
        Args:
            patience: Number of epochs to wait for improvement
            min_delta: Minimum change to qualify as improvement
            mode: 'min' (lower is better) or 'max' (higher is better)
        """
        self.patience = patience
        self.min_delta = min_delta
        self.mode = mode
        self.counter = 0
        self.best_score = float("inf") if mode == "min" else float("-inf")
        self.early_stop = False
    
    def __call__(self, score: float) -> bool:
        """
        Check if training should be stopped.
        
        Args:
            score: Current validation score
            
        Returns:
            True if training should be stopped
        """
        if self.mode == "min":
            if score < self.best_score - self.min_delta:
                self.best_score = score
                self.counter = 0
            else:
                self.counter += 1
        else:  # mode == "max"
            if score > self.best_score + self.min_delta:
                self.best_score = score
                self.counter = 0
            else:
                self.counter += 1
        
        if self.counter >= self.patience:
            self.early_stop = True
            return True
        
        return False


def get_loss_function(loss_name: str) -> Callable:
    """
    Get loss function by name.
    
    Args:
        loss_name: Name of the loss function
        
    Returns:
        Loss function callable
    """
    if loss_name == "mse":
        return nn.MSELoss()
    elif loss_name == "mae":
        return nn.L1Loss()
    elif loss_name == "huber":
        return nn.SmoothL1Loss()
    elif loss_name == "quantile":
        # Custom quantile loss implementation
        def quantile_loss(y_pred, y_true, quantiles=[0.1, 0.5, 0.9]):
            losses = []
            for i, q in enumerate(quantiles):
                errors = y_true - y_pred[:, i].unsqueeze(1)
                losses.append(torch.max(q * errors, (q - 1) * errors).unsqueeze(1))
            
            loss = torch.cat(losses, dim=1).mean()
            return loss
        
        return quantile_loss
    else:
        raise ValueError(f"Unknown loss function: {loss_name}")


def get_optimizer(
    optimizer_name: str,
    model_parameters: List[nn.Parameter],
    lr: float,
    weight_decay: float,
) -> optim.Optimizer:
    """
    Get optimizer by name.
    
    Args:
        optimizer_name: Name of the optimizer
        model_parameters: Model parameters to optimize
        lr: Learning rate
        weight_decay: Weight decay for regularization
        
    Returns:
        PyTorch optimizer
    """
    if optimizer_name.lower() == "adam":
        return optim.Adam(model_parameters, lr=lr, weight_decay=weight_decay)
    elif optimizer_name.lower() == "adamw":
        return optim.AdamW(model_parameters, lr=lr, weight_decay=weight_decay)
    elif optimizer_name.lower() == "sgd":
        return optim.SGD(model_parameters, lr=lr, weight_decay=weight_decay)
    else:
        raise ValueError(f"Unknown optimizer: {optimizer_name}")


def get_lr_scheduler(
    scheduler_name: str,
    optimizer: optim.Optimizer,
    max_epochs: int,
    **kwargs: Any,
) -> Optional[optim.lr_scheduler._LRScheduler]:
    """
    Get learning rate scheduler by name.
    
    Args:
        scheduler_name: Name of the scheduler
        optimizer: Optimizer to schedule
        max_epochs: Maximum number of epochs
        **kwargs: Additional scheduler parameters
        
    Returns:
        PyTorch learning rate scheduler
    """
    if scheduler_name.lower() == "cosine":
        return CosineAnnealingLR(optimizer, T_max=max_epochs)
    elif scheduler_name.lower() == "step":
        step_size = kwargs.get("step_size", max_epochs // 3)
        gamma = kwargs.get("gamma", 0.1)
        return StepLR(optimizer, step_size=step_size, gamma=gamma)
    elif scheduler_name.lower() == "plateau":
        return ReduceLROnPlateau(
            optimizer,
            mode="min",
            factor=kwargs.get("factor", 0.1),
            patience=kwargs.get("patience", 10),
        )
    elif scheduler_name.lower() == "constant":
        return None
    else:
        raise ValueError(f"Unknown scheduler: {scheduler_name}")


def train_epoch(
    model: nn.Module,
    train_loader: DataLoader,
    optimizer: optim.Optimizer,
    loss_fn: Callable,
    device: torch.device,
    log_every_n_steps: int = 0,
) -> Dict[str, float]:
    """
    Train for one epoch.
    
    Args:
        model: Model to train
        train_loader: Training data loader
        optimizer: Optimizer
        loss_fn: Loss function
        device: Device to train on
        log_every_n_steps: Log interval (0 to disable)
        
    Returns:
        Dictionary of training metrics
    """
    model.train()
    total_loss = 0.0
    total_samples = 0
    
    all_preds = []
    all_targets = []
    
    start_time = time.time()
    
    for step, (features, targets) in enumerate(train_loader):
        # Move data to device
        features = features.to(device)
        targets = targets.to(device)
        
        # Forward pass
        predictions = model(features)
        
        # Calculate loss
        loss = loss_fn(predictions, targets)
        
        # Backward pass and optimize
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        
        # Track metrics
        batch_size = features.size(0)
        total_loss += loss.item() * batch_size
        total_samples += batch_size
        
        # Store predictions and targets for metrics
        all_preds.append(predictions.detach().cpu().numpy())
        all_targets.append(targets.detach().cpu().numpy())
        
        # Optional logging
        if log_every_n_steps > 0 and step % log_every_n_steps == 0:
            logger.info(f"Train Step: {step}/{len(train_loader)} Loss: {loss.item():.4f}")
    
    # Calculate epoch metrics
    epoch_loss = total_loss / total_samples
    epoch_time = time.time() - start_time
    
    # Concatenate predictions and targets
    all_preds = np.concatenate(all_preds, axis=0)
    all_targets = np.concatenate(all_targets, axis=0)
    
    # Calculate additional metrics
    regression_metrics = calculate_regression_metrics(all_targets, all_preds)
    dir_accuracy = calculate_directional_accuracy(all_targets, all_preds)
    profit_factor = calculate_profit_factor(all_targets, all_preds)
    
    # Combine metrics
    metrics = {
        "loss": epoch_loss,
        "dir_accuracy": dir_accuracy,
        "profit_factor": profit_factor,
        "time": epoch_time,
        **regression_metrics,
    }
    
    return metrics


def evaluate(
    model: nn.Module,
    data_loader: DataLoader,
    loss_fn: Callable,
    device: torch.device,
) -> Dict[str, float]:
    """
    Evaluate model on validation or test data.
    
    Args:
        model: Model to evaluate
        data_loader: Validation/test data loader
        loss_fn: Loss function
        device: Device to evaluate on
        
    Returns:
        Dictionary of evaluation metrics
    """
    model.eval()
    total_loss = 0.0
    total_samples = 0
    
    all_preds = []
    all_targets = []
    
    with torch.no_grad():
        for features, targets in data_loader:
            # Move data to device
            features = features.to(device)
            targets = targets.to(device)
            
            # Forward pass
            predictions = model(features)
            
            # Calculate loss
            loss = loss_fn(predictions, targets)
            
            # Track metrics
            batch_size = features.size(0)
            total_loss += loss.item() * batch_size
            total_samples += batch_size
            
            # Store predictions and targets for metrics
            all_preds.append(predictions.detach().cpu().numpy())
            all_targets.append(targets.detach().cpu().numpy())
    
    # Calculate epoch metrics
    epoch_loss = total_loss / total_samples
    
    # Concatenate predictions and targets
    all_preds = np.concatenate(all_preds, axis=0)
    all_targets = np.concatenate(all_targets, axis=0)
    
    # Calculate additional metrics
    regression_metrics = calculate_regression_metrics(all_targets, all_preds)
    dir_accuracy = calculate_directional_accuracy(all_targets, all_preds)
    profit_factor = calculate_profit_factor(all_targets, all_preds)
    
    # Combine metrics
    metrics = {
        "loss": epoch_loss,
        "dir_accuracy": dir_accuracy,
        "profit_factor": profit_factor,
        **regression_metrics,
    }
    
    return metrics


def save_checkpoint(
    model: nn.Module,
    optimizer: optim.Optimizer,
    epoch: int,
    metrics: Dict[str, float],
    save_path: Union[str, Path],
    model_name: str,
) -> Path:
    """
    Save model checkpoint.
    
    Args:
        model: Model to save
        optimizer: Optimizer state
        epoch: Current epoch
        metrics: Latest metrics
        save_path: Directory to save checkpoint
        model_name: Name for the checkpoint file
        
    Returns:
        Path to the saved checkpoint
    """
    save_dir = Path(save_path)
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # Create checkpoint filename
    filename = f"{model_name}_epoch_{epoch}.pt"
    filepath = save_dir / filename
    
    # Save checkpoint
    checkpoint = {
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "metrics": metrics,
    }
    
    torch.save(checkpoint, filepath)
    logger.info(f"Model checkpoint saved to {filepath}")
    
    return filepath


def load_checkpoint(
    model: nn.Module,
    optimizer: Optional[optim.Optimizer],
    filepath: Union[str, Path],
    device: Optional[torch.device] = None,
) -> Tuple[nn.Module, Optional[optim.Optimizer], int, Dict[str, float]]:
    """
    Load model checkpoint.
    
    Args:
        model: Model instance to load weights into
        optimizer: Optional optimizer to load state
        filepath: Path to checkpoint file
        device: Device to load model on
        
    Returns:
        Tuple of (model, optimizer, epoch, metrics)
    """
    # Determine device
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    # Load checkpoint
    checkpoint = torch.load(filepath, map_location=device)
    
    # Load model state
    model.load_state_dict(checkpoint["model_state_dict"])
    
    # Load optimizer state if provided
    if optimizer is not None and "optimizer_state_dict" in checkpoint:
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
    
    # Get epoch and metrics
    epoch = checkpoint.get("epoch", 0)
    metrics = checkpoint.get("metrics", {})
    
    logger.info(f"Loaded model checkpoint from {filepath} (epoch {epoch})")
    
    return model, optimizer, epoch, metrics


class ForecasterTrainer:
    """
    Trainer for the forecaster model.
    
    Handles the complete training lifecycle including
    initialization, training loop, evaluation, and checkpointing.
    """
    
    def __init__(
        self,
        model: TimeSeriesForecaster,
        config: ForecasterConfig,
    ) -> None:
        """
        Initialize trainer.
        
        Args:
            model: Model to train
            config: Training configuration
        """
        self.model = model
        self.config = config
        
        # Set up device
        self.device = torch.device(config.training.device if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")
        
        # Ensure model is on correct device
        self.model = self.model.to(self.device)
        
        # Initialize optimizer, loss function, and scheduler
        self.optimizer = get_optimizer(
            optimizer_name=config.training.optimizer,
            model_parameters=model.parameters(),
            lr=config.training.learning_rate,
            weight_decay=config.training.weight_decay,
        )
        
        self.loss_fn = get_loss_function(config.training.loss_fn)
        
        self.lr_scheduler = get_lr_scheduler(
            scheduler_name=config.training.lr_scheduler,
            optimizer=self.optimizer,
            max_epochs=config.training.max_epochs,
        )
        
        # Set up early stopping
        self.early_stopping = EarlyStopping(
            patience=config.training.early_stopping_patience,
            mode="min",
        )
        
        # Training state
        self.current_epoch = 0
        self.best_val_loss = float("inf")
        self.train_metrics_history = []
        self.val_metrics_history = []
        
        logger.info("Trainer initialized")
    
    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
    ) -> Dict[str, List[float]]:
        """
        Train the model.
        
        Args:
            train_loader: Training data loader
            val_loader: Validation data loader
            
        Returns:
            Dictionary of training history
        """
        logger.info(f"Starting training for {self.config.training.max_epochs} epochs")
        
        # Main training loop
        for epoch in range(self.current_epoch, self.config.training.max_epochs):
            self.current_epoch = epoch
            
            # Train for one epoch
            train_metrics = train_epoch(
                model=self.model,
                train_loader=train_loader,
                optimizer=self.optimizer,
                loss_fn=self.loss_fn,
                device=self.device,
                log_every_n_steps=self.config.training.log_every_n_steps,
            )
            
            # Evaluate on validation set
            val_metrics = evaluate(
                model=self.model,
                data_loader=val_loader,
                loss_fn=self.loss_fn,
                device=self.device,
            )
            
            # Update learning rate scheduler if using
            if self.lr_scheduler is not None:
                if isinstance(self.lr_scheduler, ReduceLROnPlateau):
                    self.lr_scheduler.step(val_metrics["loss"])
                else:
                    self.lr_scheduler.step()
            
            # Log metrics
            log_metrics(train_metrics, prefix="Train ", level="info")
            log_metrics(val_metrics, prefix="Validation ", level="info")
            
            # Store metrics history
            self.train_metrics_history.append(train_metrics)
            self.val_metrics_history.append(val_metrics)
            
            # Save checkpoint if improved
            if val_metrics["loss"] < self.best_val_loss:
                self.best_val_loss = val_metrics["loss"]
                logger.info(f"New best validation loss: {self.best_val_loss:.6f}")
                
                save_checkpoint(
                    model=self.model,
                    optimizer=self.optimizer,
                    epoch=epoch,
                    metrics=val_metrics,
                    save_path=self.config.training.checkpoint_dir,
                    model_name=f"{self.config.experiment_name}_best",
                )
            
            # Regular checkpoint saving (every N epochs)
            if (epoch + 1) % 5 == 0:
                save_checkpoint(
                    model=self.model,
                    optimizer=self.optimizer,
                    epoch=epoch,
                    metrics=val_metrics,
                    save_path=self.config.training.checkpoint_dir,
                    model_name=f"{self.config.experiment_name}_epoch{epoch+1}",
                )
            
            # Check for early stopping
            if self.early_stopping(val_metrics["loss"]):
                logger.info(f"Early stopping triggered after {epoch+1} epochs")
                break
        
        # Save final model
        save_checkpoint(
            model=self.model,
            optimizer=self.optimizer,
            epoch=self.current_epoch,
            metrics=val_metrics,
            save_path=self.config.model_save_path,
            model_name=f"{self.config.experiment_name}_final",
        )
        
        logger.info(f"Training completed after {self.current_epoch+1} epochs")
        
        # Return training history
        history = {
            "train_loss": [m["loss"] for m in self.train_metrics_history],
            "val_loss": [m["loss"] for m in self.val_metrics_history],
            "train_dir_acc": [m["dir_accuracy"] for m in self.train_metrics_history],
            "val_dir_acc": [m["dir_accuracy"] for m in self.val_metrics_history],
        }
        
        return history
    
    def evaluate_test_set(
        self,
        test_loader: DataLoader,
    ) -> Dict[str, float]:
        """
        Evaluate model on test set.
        
        Args:
            test_loader: Test data loader
            
        Returns:
            Dictionary of test metrics
        """
        logger.info("Evaluating model on test set")
        
        # Load best model if available
        best_model_path = Path(self.config.training.checkpoint_dir) / f"{self.config.experiment_name}_best.pt"
        if best_model_path.exists():
            self.model, _, _, _ = load_checkpoint(
                model=self.model,
                optimizer=None,
                filepath=best_model_path,
                device=self.device,
            )
        
        # Evaluate on test set
        test_metrics = evaluate(
            model=self.model,
            data_loader=test_loader,
            loss_fn=self.loss_fn,
            device=self.device,
        )
        
        # Log test metrics
        log_metrics(test_metrics, prefix="Test ", level="info")
        
        return test_metrics
    
    def save_final_model(self) -> Path:
        """
        Save the final model for production use.
        
        Returns:
            Path to the saved model
        """
        logger.info("Saving final model for production")
        
        # Create save directory
        save_dir = Path(self.config.model_save_path)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model
        model_path = save_dir / f"{self.config.experiment_name}.pt"
        
        # Save just the model state dict for production use
        torch.save(self.model.state_dict(), model_path)
        
        logger.info(f"Final model saved to {model_path}")
        
        return model_path


def train_forecaster(
    config: ForecasterConfig,
    model: TimeSeriesForecaster,
    train_loader: DataLoader,
    val_loader: DataLoader,
    test_loader: Optional[DataLoader] = None,
) -> Tuple[TimeSeriesForecaster, Dict[str, Any]]:
    """
    Complete training pipeline for the forecaster model.
    
    Args:
        config: Forecaster configuration
        model: Model to train
        train_loader: Training data loader
        val_loader: Validation data loader
        test_loader: Optional test data loader
        
    Returns:
        Tuple of (trained model, results dictionary)
    """
    # Initialize trainer
    trainer = ForecasterTrainer(model=model, config=config)
    
    # Train model
    training_history = trainer.train(
        train_loader=train_loader,
        val_loader=val_loader,
    )
    
    # Evaluate on test set if provided
    test_metrics = {}
    if test_loader is not None:
        test_metrics = trainer.evaluate_test_set(test_loader=test_loader)
    
    # Save final model
    final_model_path = trainer.save_final_model()
    
    # Compile results
    results = {
        "training_history": training_history,
        "test_metrics": test_metrics,
        "final_model_path": str(final_model_path),
        "best_val_loss": trainer.best_val_loss,
        "epochs_trained": trainer.current_epoch + 1,
    }
    
    return model, results 