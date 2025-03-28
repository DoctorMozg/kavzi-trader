"""
Base model class for KavziTrader.

This module provides the abstract base class for machine learning models used in
KavziTrader.
It establishes a consistent interface that all model implementations must follow.
"""

import abc
import json
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

import numpy as np
from numpy.typing import NDArray

from src.models.config import ModelConfigSchema
from src.models.metrics import TrainingMetricsSchema

T = TypeVar("T", bound=ModelConfigSchema)


class BaseNnModel(abc.ABC, Generic[T]):
    """
    Abstract base class for all machine learning models in KavziTrader.

    All model implementations must inherit from this class and implement
    its abstract methods to ensure a consistent interface.
    """

    # Class attributes
    MODEL_TYPE: ClassVar[str] = "base"
    VERSION: ClassVar[str] = "0.1.0"

    def __init__(self, name: str, config: T) -> None:
        """
        Initialize the base model.

        Args:
            name: Unique identifier for this model instance
            config: Configuration parameters for the model
        """
        self.name = name
        self.config = config
        self.metrics = TrainingMetricsSchema()  # type: ignore[call-arg]

    @abc.abstractmethod
    def train(
        self,
        features: NDArray[np.float32],
        targets: NDArray[np.float32],
    ) -> TrainingMetricsSchema:
        """
        Train the model on the provided data.

        Args:
            features: Array of feature vectors
            targets: Array of target values

        Returns:
            Training metrics
        """

    @abc.abstractmethod
    def predict(self, features: NDArray[np.float32]) -> NDArray[np.float32]:
        """
        Generate predictions for the provided features.

        Args:
            features: Array of feature vectors

        Returns:
            Array of predicted values
        """

    def save(self, directory: Path) -> Path:
        """
        Save the model to disk.

        Args:
            directory: Directory to save the model

        Returns:
            Path to the saved model
        """
        path = directory / f"{self.name}.json"
        metadata = {
            "name": self.name,
            "model_type": self.MODEL_TYPE,
            "version": self.VERSION,
            "config": self.config.model_dump(),
            "metrics": self.metrics.model_dump(),
        }

        directory.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(metadata, f, indent=2)

        self._save_model_specific(directory)
        return path

    @abc.abstractmethod
    def _save_model_specific(self, directory: Path) -> None:
        """
        Save model-specific data to disk.

        Args:
            directory: Directory to save model-specific data
        """

    @classmethod
    @abc.abstractmethod
    def load(cls, directory: Path, name: str) -> "BaseNnModel[T]":
        """
        Load a model from disk.

        Args:
            directory: Directory where the model is saved
            name: Name of the model to load

        Returns:
            Loaded model instance
        """

    def update_metrics(self, metrics: TrainingMetricsSchema) -> None:
        """
        Update the model's performance metrics.

        Args:
            metrics: Metrics schema with training performance data
        """
        self.metrics = metrics
