"""
Model-related database models for SQLAlchemy.

This module defines SQLAlchemy models for ML models and related entities.
These models map to the database tables for storing model metadata and training runs.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import (
    Boolean,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.storage.models.base import BaseModel


class ModelModel(BaseModel):
    """
    SQLAlchemy model for models table.

    Stores metadata for machine learning models.
    """

    __tablename__ = "models"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    architecture: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    hyperparameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    # Relationships
    training_runs: Mapped[list["ModelTrainingRunModel"]] = relationship(
        "ModelTrainingRunModel",
        back_populates="model",
        cascade="all, delete-orphan",
    )
    strategies: Mapped[list["StrategyModel"]] = relationship(
        "StrategyModel",
        back_populates="model",
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("name", "version", name="uix_model_name_version"),
    )

    @property
    def file_path_obj(self) -> Path:
        """Get the file path as a Path object."""
        return Path(self.file_path)

    def get_best_training_run(self) -> "ModelTrainingRunModel | None":
        """
        Get the best training run for this model.

        Returns the training run with the lowest validation loss.

        Returns:
            The best training run or None if no training runs exist
        """
        if not self.training_runs:
            return None

        # Find run with lowest validation loss
        return min(
            [run for run in self.training_runs if run.validation_metrics is not None],
            key=lambda run: run.validation_metrics.get("loss", float("inf")),  # type: ignore
            default=None,
        )


class ModelTrainingRunModel(BaseModel):
    """
    SQLAlchemy model for model_training_runs table.

    Stores information about model training runs.
    """

    __tablename__ = "model_training_runs"

    model_id: Mapped[int] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_time: Mapped[datetime] = mapped_column(nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(nullable=True)
    epochs: Mapped[int] = mapped_column(nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    train_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    validation_metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    dataset_info: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # Relationships
    model: Mapped["ModelModel"] = relationship(
        "ModelModel",
        back_populates="training_runs",
    )

    @property
    def is_completed(self) -> bool:
        """Check if the training run was completed."""
        return cast(bool, self.status == "COMPLETED")

    @property
    def is_best_run(self) -> bool:
        """Check if this is the best training run for the model."""
        if not self.model:
            return False

        best_run = self.model.get_best_training_run()
        return best_run is not None and best_run.id == self.id

    @property
    def duration_seconds(self) -> float | None:
        """
        Calculate the duration of the training run in seconds.

        Returns:
            Duration in seconds or None if end_time is not set
        """
        if self.end_time is None or self.start_time is None:
            return None

        return cast(float, (self.end_time - self.start_time).total_seconds())

    @classmethod
    def create_from_metrics(
        cls,
        model_id: int,
        epochs: int,
        parameters: dict[str, Any],
        dataset_info: dict[str, Any],
        train_metrics: dict[str, Any] | None = None,
        validation_metrics: dict[str, Any] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status: str = "PENDING",
    ) -> "ModelTrainingRunModel":
        """
        Create a training run from metrics.

        Args:
            model_id: ID of the model
            epochs: Number of epochs trained
            parameters: Training parameters
            dataset_info: Information about the dataset
            train_metrics: Training metrics
            validation_metrics: Validation metrics
            start_time: Training start time, defaults to current time
            end_time: Training end time
            status: Status of the training run

        Returns:
            ModelTrainingRunModel instance
        """
        from src.commons.time_utility import now_ts

        if start_time is None:
            start_time = now_ts()

        return cls(
            model_id=model_id,
            start_time=start_time,
            end_time=end_time,
            epochs=epochs,
            parameters=parameters,
            train_metrics=train_metrics,
            validation_metrics=validation_metrics,
            dataset_info=dataset_info,
            status=status,
        )
