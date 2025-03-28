"""
Model metrics for KavziTrader.

This module provides Pydantic schemas for model metrics and performance tracking.
"""

from typing import Annotated

from pydantic import Field

from src.commons.datetime_schema import TimestampedSchema


class MetricsSchema(TimestampedSchema):
    """Base schema for tracking model metrics."""

    # Basic metrics
    train_loss: Annotated[float | None, Field(None)]
    val_loss: Annotated[float | None, Field(None)]
    test_loss: Annotated[float | None, Field(None)]

    # Additional metrics can be added by specific models
    additional_metrics: Annotated[dict[str, float], Field(default_factory=dict)]


class TrainingMetricsSchema(MetricsSchema):
    """Schema for tracking model training performance."""

    # Training process metrics
    train_loss_history: Annotated[list[float], Field(default_factory=list)]
    val_loss_history: Annotated[list[float], Field(default_factory=list)]
    epochs_trained: Annotated[int, Field(0)]
    best_epoch: Annotated[int, Field(0)]
    early_stopped: Annotated[bool, Field(False)]

    # Best performance
    best_val_loss: Annotated[float | None, Field(None)]
    final_train_loss: Annotated[float | None, Field(None)]
    final_val_loss: Annotated[float | None, Field(None)]

    def add_epoch_results(self, train_loss: float, val_loss: float) -> None:
        """
        Add results from a training epoch.

        Args:
            train_loss: Training loss for this epoch
            val_loss: Validation loss for this epoch
        """
        self.train_loss_history.append(train_loss)
        self.val_loss_history.append(val_loss)

        # Update final metrics
        self.final_train_loss = train_loss
        self.final_val_loss = val_loss
        self.train_loss = train_loss
        self.val_loss = val_loss

        # Check if this is the best epoch
        if self.best_val_loss is None or val_loss < self.best_val_loss:
            self.best_val_loss = val_loss
            self.best_epoch = len(self.val_loss_history) - 1

        # Update epochs trained
        self.epochs_trained = len(self.val_loss_history)


class PredictionMetricsSchema(MetricsSchema):
    """Schema for tracking model prediction performance."""

    mse: Annotated[float | None, Field(None)]
    rmse: Annotated[float | None, Field(None)]
    mae: Annotated[float | None, Field(None)]
    r2: Annotated[float | None, Field(None)]

    # Trading-specific metrics
    direction_accuracy: Annotated[
        float | None,
        Field(None),
    ]  # Percentage of correct price movement directions
    profit_factor: Annotated[float | None, Field(None)]  # Gross profit / Gross loss
    max_drawdown: Annotated[float | None, Field(None)]  # Maximum peak to trough decline
    sharpe_ratio: Annotated[float | None, Field(None)]  # Risk-adjusted return
